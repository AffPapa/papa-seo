#!/usr/bin/env python3
"""Structured data of one page: what is marked up and what is wrong with it. JSON out.

    python3 scripts/schema_check.py page.html [--base-url https://site/page] [--out schema.json]
    python3 scripts/schema_check.py https://site/page [--out schema.json]   # one GET via http_safe
    python3 scripts/schema_check.py data.json            # a JSON-LD document on its own
    python3 scripts/schema_check.py --list-checks        # the contract: every check and its source

Deterministic only: JSON-LD is parsed (never executed), values are compared with the shapes the
sources below demand. Nothing is fetched beyond the one page.

Sources. The required/recommended split for each of the 22 types was read off that type's page on
developers.google.com on 30.10.2026; the summary with dates is in `references/facts-2026.md` §6.
Where the documentation says «There are no required properties» — Article, Organization — the check
calls the properties recommended, stands at severity low, and says so in the note. A type whose
documentation Google has withdrawn (FAQPage, sitelinks searchbox) carries no requirements at all.
Calling a recommendation a requirement is the error this script is built not to make.
Type and property names come from schema.org (names only — the vocabulary descriptions are
CC BY-SA 3.0 and are not copied here).

Security (SPEC §2 rule 4): the markup is data. Text inside it that addresses a model is reported by
page_facts.py as `hidden_instruction`; here every extracted string is printed with invisible
characters escaped.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_safe  # noqa: E402
import page_facts  # noqa: E402
import ru_text  # noqa: E402

_plural = ru_text.plural
_qty = ru_text.num

MAX_ENTITIES = 500
MAX_DEPTH = 40
MAX_ROWS = 2000
REGISTRY_VERSION = "0.2.2"

S_SDP = ("Google «Structured data general guidelines» (developers.google.com/search/docs/appearance/"
         "structured-data/sd-policies); facts-2026 §6")
S_SCHEMA = "schema.org (schema.org/docs/gs.html) — словарь обязательных свойств не задаёт"
S_JSONLD = "w3.org/TR/json-ld11/"
S_ISO8601 = "ISO 8601 (дата и время)"
S_MERCHANT = ("Google structured data: Offer / merchant listing (developers.google.com/search/docs/"
              "appearance/structured-data/merchant-listing); facts-2026 §6")
S_REVIEWSNIP = ("Google structured data: Review snippet (developers.google.com/search/docs/appearance/"
                "structured-data/review-snippet); facts-2026 §6")
S_EDITOR = "ориентир редактора"


def _gsd(name: str, slug: str) -> str:
    return (f"Google structured data: {name} (developers.google.com/search/docs/appearance/"
            f"structured-data/{slug}); словарь — schema.org; facts-2026 §6")


# id -> (group, title, how, severity, source, registry)
CHECK_META: dict[str, tuple[str, str, str, str, str, str]] = {
    "markup.jsonld_present": ("markup", "разметка есть вообще",
                              "сколько блоков JSON-LD, типов microdata и RDFa найдено", "info",
                              S_SDP, "contract"),
    "markup.jsonld_parses": ("markup", "JSON-LD разбирается",
                             "каждый блок application/ld+json — корректный JSON", "high", S_JSONLD,
                             "contract"),
    "markup.jsonld_context": ("markup", "@context указан",
                              "@context задан и указывает на schema.org", "high", S_JSONLD, "contract"),
    "markup.jsonld_type": ("markup", "@type указан",
                           "у каждой сущности есть @type, имя типа — UpperCamelCase", "high",
                           S_JSONLD + "; " + S_SCHEMA, "contract"),
    "markup.jsonld_depth": ("markup", "глубина и размер блока",
                            "самая глубокая ветка и число сущностей", "info", S_EDITOR, "contract"),
    "markup.format_preference": ("markup", "формат разметки",
                                 "какие из трёх форматов найдены; JSON-LD — рекомендованный Google, "
                                 "Яндекс часть типов берёт только из микроданных", "info", S_SDP,
                                 "contract"),
    "markup.schemaorg_vocab": ("markup", "свойства есть в словаре",
                               "имена свойств узла против нашего списка известных для schema.org; "
                               "неизвестные — в список", "low", S_SCHEMA, "contract"),
    "markup.placeholders": ("markup", "плейсхолдеры в значениях",
                            "значения вида \"\", null, \"N/A\", \"undefined\", \"не указано\"",
                            "medium", S_SDP, "contract"),
    "markup.date_format": ("markup", "формат дат в разметке",
                           "датные свойства разбираются как ISO 8601", "medium",
                           S_ISO8601 + "; " + S_SDP, "contract"),
    "markup.relative_urls": ("markup", "относительные URL в разметке",
                             "url/sameAs/logo/contentUrl/embedUrl начинаются со схемы", "medium",
                             S_SDP, "contract"),
    "markup.price_format": ("markup", "формат цены",
                            "Offer.price приводится к числу и больше нуля; валюта отдельно в "
                            "priceCurrency (ISO 4217)", "medium", S_MERCHANT, "contract"),
    "markup.id_duplicate": ("markup", "дубли @id", "одно значение @id у разных узлов", "low",
                            S_JSONLD, "contract"),
    "markup.id_dangling": ("markup", "висячие ссылки @id",
                           "{\"@id\": …} без узла с таким @id в документе", "low", S_JSONLD,
                           "contract"),
    "markup.url_vs_canonical": ("markup", "url разметки против canonical",
                                "значение url/mainEntityOfPage против canonical страницы", "low",
                                S_SDP, "contract"),
    "markup.retired_type": ("markup", "выведенный тип ради выдачи",
                            "сверка типов страницы со списком снятых функций в facts-2026", "medium",
                            "facts-2026 §6", "contract"),
    "markup.visible_values": ("markup", "значения видны на странице",
                              "name, headline, price, ratingValue из разметки ищутся в видимом тексте",
                              "high", S_SDP, "contract"),
    "markup.sd_self_serving": ("markup", "отзывы о себе",
                               "review/aggregateRating у Organization или LocalBusiness", "medium",
                               S_REVIEWSNIP + " (обновление 08.09.2026)", "contract"),
    "markup.yandex_supported": ("markup", "тип поддержан Яндексом",
                                "типы против списка поддерживаемых схем Яндекса "
                                "(references/yandex.md §4); FAQPage там нет", "low",
                                "Яндекс: поддерживаемые схемы и Open Graph "
                                "(yandex.ru/support/webmaster/); references/yandex.md §4",
                                "contract"),
    "markup.duplicate_types": ("markup", "один главный тип в нескольких сущностях",
                               "Organization/WebSite/WebPage/BreadcrumbList встречается больше раза",
                               "info", S_EDITOR, "contract"),
    "commerce.aggregate_offer_misuse": ("commerce", "AggregateOffer на странице продажи",
                                        "AggregateOffer внутри Product с offers", "medium",
                                        S_MERCHANT, "contract"),
}

# ------------------------------------------------- поля типов (markup.req_*): что требует документация
# Состав списков сверен со страницами developers.google.com 30.10.2026, сводка — в facts-2026 §6.
# `doc_required: False` — у типа в документации Google раздела Required НЕТ (дословно: «There are no
# required properties»). Для таких типов мы не говорим «обязательные» ни в выводе, ни в реестре:
# находка звучит «Google рекомендует, на странице нет» и стоит low. Это правило пакета, а не стиль:
# совет, выданный за требование, — та самая неправда, которую мы ловим у чужих скилов.
# Запись в required/recommended: "prop" | ("any", [props]) | ("deep", prop, subprop) | ("special", key)
REQ_RULES: list[dict] = [
    {"id": "markup.req_article", "title": "Article / NewsArticle / BlogPosting",
     "types": {"Article", "NewsArticle", "BlogPosting", "TechArticle", "Report", "ScholarlyArticle"},
     "doc_required": False, "required": [],
     "recommended": ["headline", "image", "datePublished", "dateModified",
                     ("deep", "author", "name"), ("deep", "author", "url")],
     "source": _gsd("Article", "article")},
    {"id": "markup.req_organization", "title": "Organization",
     "types": {"Organization", "NewsMediaOrganization", "OnlineBusiness", "Corporation"},
     "doc_required": False, "required": [],
     "recommended": ["name", "url", "logo", "sameAs", "address", "contactPoint", "description",
                     "legalName", "telephone"],
     "source": _gsd("Organization", "organization")},
    {"id": "markup.req_breadcrumb", "title": "BreadcrumbList", "types": {"BreadcrumbList"},
     "doc_required": True, "required": [("special", "breadcrumb")], "recommended": [],
     "note": "`name` у ListItem документация не требует в отдельных случаях — смотрите страницу типа",
     "source": _gsd("BreadcrumbList", "breadcrumb")},
    {"id": "markup.req_product", "title": "Product (product snippet)", "types": {"Product"},
     "doc_required": True,
     "required": ["name", ("any", ["review", "aggregateRating", "offers"])],
     "recommended": ["image", "description", "sku", "brand", "gtin", "category"],
     "source": _gsd("Product", "product-snippet")},
    {"id": "markup.req_offer", "title": "Offer / merchant listing", "types": {"Product"},
     "when": "has_offers", "doc_required": True,
     "required": ["name", "image", "offers", ("special", "offer_price")],
     "recommended": ["availability", "itemCondition", "shippingDetails", "hasMerchantReturnPolicy",
                     "priceValidUntil", "url"],
     "recommended_in": "offers", "source": S_MERCHANT},
    {"id": "markup.req_person", "title": "Person / ProfilePage", "types": {"Person", "ProfilePage"},
     "doc_required": True, "required": [("special", "person")],
     "recommended": ["image", "sameAs", "alternateName", "description", "identifier"],
     "source": _gsd("Profile page", "profile-page")},
    {"id": "markup.req_event", "title": "Event",
     "types": {"Event", "BusinessEvent", "EducationEvent", "Festival", "SportsEvent",
               "MusicEvent", "TheaterEvent", "ExhibitionEvent", "SocialEvent"},
     "doc_required": True,
     "required": ["name", "startDate", ("special", "event_location")],
     "recommended": ["description", "endDate", "eventStatus", "image", "offers", "organizer",
                     "performer"],
     "source": _gsd("Event", "event")},
    {"id": "markup.req_jobposting", "title": "JobPosting", "types": {"JobPosting"},
     "doc_required": True,
     "required": ["title", "description", "datePosted", "hiringOrganization",
                  ("special", "job_location")],
     "recommended": ["validThrough", "baseSalary", "employmentType", "identifier",
                     "jobLocationType", "directApply"],
     "source": _gsd("JobPosting", "job-posting")},
    {"id": "markup.req_localbusiness", "title": "LocalBusiness", "types": {"LocalBusiness"},
     # подтипы LocalBusiness в schema.org исчисляются сотнями: берём распространённые окончания
     "types_suffix": ("Business", "Store", "Shop", "Restaurant", "Hotel", "Clinic", "Agency",
                      "Market", "Bar", "Cafe", "Salon", "Gym", "Pharmacy", "Dealer", "Service"),
     "doc_required": True, "required": ["name", "address"],
     "recommended": ["telephone", "openingHoursSpecification", "geo", "url", "priceRange",
                     "aggregateRating", "review", "department"],
     "source": _gsd("Local business", "local-business")},
    {"id": "markup.req_recipe", "title": "Recipe", "types": {"Recipe"},
     "doc_required": True, "required": ["name", "image"],
     "recommended": ["author", "datePublished", "description", "keywords", "recipeIngredient",
                     "recipeInstructions", "prepTime", "cookTime", "totalTime", "recipeYield",
                     "recipeCategory", "recipeCuisine", "nutrition", "aggregateRating", "video"],
     "source": _gsd("Recipe", "recipe")},
    {"id": "markup.req_videoobject", "title": "VideoObject", "types": {"VideoObject"},
     "doc_required": True, "required": ["name", "thumbnailUrl", "uploadDate"],
     "recommended": ["description", "duration", "contentUrl", "embedUrl", "creator", "expires",
                     "interactionStatistic", "regionsAllowed"],
     "source": _gsd("Video", "video")},
    {"id": "markup.req_website", "title": "WebSite + SearchAction (функция выведена)",
     "types": {"WebSite"}, "when": "has_searchaction", "doc_required": False,
     "required": [], "recommended": [], "retired": True,
     "note": "Документация Sitelinks search box снята 29.11.2024: «The sitelinks search box feature "
             "is no longer available in Google Search results». Требований к SearchAction у Google "
             "больше нет, разметка не вредит, но карточки в выдаче не даёт (facts-2026 §6)",
     "source": "Google Search updates, 29.11.2024 (developers.google.com/search/updates); "
               "facts-2026 §6"},
    {"id": "markup.req_itemlist", "title": "ItemList / Carousel", "types": {"ItemList"},
     "skip_types": {"BreadcrumbList"}, "doc_required": True,
     "required": [("special", "itemlist")], "recommended": ["name", "numberOfItems"],
     "note": "Документация требует либо `position` + `url` (сводная страница), либо "
             "`item` с `item.name` и `item.url` (всё на одной странице)",
     "source": _gsd("Carousel", "carousel")},
    {"id": "markup.req_qapage", "title": "QAPage", "types": {"QAPage"}, "doc_required": True,
     "required": [("special", "question_page_qa")],
     "recommended": ["author", "upvoteCount", "datePublished", "dateModified", "image", "text"],
     "recommended_in": "mainEntity", "source": _gsd("Q&A", "qapage")},
    {"id": "markup.req_review", "title": "Review / AggregateRating",
     "types": {"Review", "AggregateRating"}, "doc_required": True,
     "required": [("special", "review")],
     "recommended": ["bestRating", "worstRating", "datePublished"],
     # datePublished — свойство отзыва, у агрегата его не ждут
     "recommended_skip": {"AggregateRating": {"datePublished"}}, "source": S_REVIEWSNIP},
    {"id": "markup.req_softwareapp", "title": "SoftwareApplication",
     "types": {"SoftwareApplication", "MobileApplication", "WebApplication", "VideoGame"},
     "doc_required": True,
     "required": ["name", ("special", "app_price"), ("any", ["aggregateRating", "review"])],
     "recommended": ["applicationCategory", "operatingSystem", "screenshot", "softwareVersion"],
     "source": _gsd("Software app", "software-app")},
    {"id": "markup.req_faqpage", "title": "FAQPage", "types": {"FAQPage"}, "doc_required": False,
     "required": [], "recommended": [("special", "question_page_faq")],
     "note": "Документация FAQPage снята 15.06.2026, rich result не показывается с 07.05.2026, у "
             "Яндекса тип не поддержан (facts-2026 §6). Требований Google к этому типу сейчас нет; "
             "строение проверяем по словарю schema.org — это ориентир, а не требование",
     "source": "schema.org/FAQPage; facts-2026 §6 (документация Google снята 15.06.2026)"},
    {"id": "markup.req_discussion", "title": "DiscussionForumPosting",
     "types": {"DiscussionForumPosting", "SocialMediaPosting"}, "doc_required": True,
     "required": [("deep", "author", "name"), "datePublished",
                  ("any", ["text", "image", "video"])],
     "recommended": ["headline", "url", "interactionStatistic", "comment", "commentCount",
                     "dateModified", "isPartOf"],
     "source": _gsd("Discussion forum", "discussion-forum")},
    {"id": "markup.req_dataset", "title": "Dataset", "types": {"Dataset"}, "doc_required": True,
     "required": ["name", "description"],
     "recommended": ["creator", "license", "identifier", "keywords", "url", "sameAs",
                     "isAccessibleForFree", "variableMeasured", "temporalCoverage"],
     "note": "Жив только для Dataset Search, не для веб-выдачи (facts-2026 §6)",
     "source": _gsd("Dataset", "dataset")},
    {"id": "markup.req_imagelicense", "title": "ImageObject: лицензия", "types": {"ImageObject"},
     "when": "claims_license", "doc_required": True,
     "required": ["contentUrl",
                  ("any", ["license", "creator", "creditText", "copyrightNotice"])],
     "recommended": ["acquireLicensePage", "license", "creator", "creditText", "copyrightNotice"],
     "source": _gsd("Image metadata", "image-license-metadata")},
    {"id": "markup.req_speakable", "title": "speakable", "types": set(), "when": "has_speakable",
     "doc_required": True, "required": [("special", "speakable")], "recommended": [],
     "note": "Функция в бете, только новости и ограниченный набор языков",
     "source": _gsd("Speakable", "speakable")},
    {"id": "markup.req_paywall", "title": "Платный контент (paywalledContent)", "types": set(),
     "when": "has_paywall", "doc_required": True, "required": ["isAccessibleForFree"],
     "recommended": [("special", "paywall_part")],
     "note": "Без `hasPart` с `cssSelector` закрытой части закрытый текст в разметке читается "
             "как клоакинг",
     "source": _gsd("Paywalled content", "paywalled-content")},
]
for _r in REQ_RULES:
    _hard = _r.get("doc_required", True)
    CHECK_META[_r["id"]] = (
        "markup", ("Обязательные и рекомендуемые поля: " if _hard else "Рекомендуемые поля: ")
        + _r["title"],
        ("при наличии типа на странице проверить обязательные свойства из документации Google; "
         "рекомендуемые — отдельным списком severity low"
         if _hard else
         "раздела Required у этого типа в документации Google нет: проверяются только "
         "рекомендуемые свойства, их отсутствие — не нарушение требования"),
        "medium" if _hard else "low", _r["source"], "contract")

# references/yandex.md §4 — что Яндекс берёт из разметки. FAQPage там нет.
YANDEX_SUPPORTED = {
    "Organization", "Place", "LocalBusiness", "BreadcrumbList", "QAPage", "SoftwareApplication",
    "MobileApplication", "WebApplication", "VideoGame", "CreativeWork", "Recipe", "Product",
    "Offer", "AggregateOffer", "OfferCatalog", "Movie", "VideoObject", "PostalAddress",
    "ContactPoint", "AggregateRating", "Review", "Person", "ListItem", "Rating", "GeoCoordinates",
    "ImageObject", "Brand", "OpeningHoursSpecification", "WebSite", "WebPage", "Answer", "Question",
}

# «Снято» — по facts-2026 §6 с датами. Своих дат не придумываем.
RETIRED = {
    "FAQPage": "FAQ rich result объявлен 08.05.2026, не показывается с 07.05.2026, документация снята "
               "15.06.2026. Разметка не вредит, но карточек в выдаче не даёт.",
    "HowTo": "HowTo: с 13.09.2023 не показывается.",
    "ClaimReview": "Объявлен вывод 12.06.2025, снят из отчётов 09.09.2025.",
    "Course": "Course Info: объявлен вывод 12.06.2025, снят из отчётов 09.09.2025.",
    "EstimatedSalary": "Объявлен вывод 12.06.2025, снят из отчётов 09.09.2025.",
    "LearningResource": "Learning Video: объявлен вывод 12.06.2025, снят из отчётов 09.09.2025.",
    "SpecialAnnouncement": "Объявлен вывод 12.06.2025, снят из отчётов 09.09.2025.",
    "Vehicle": "Vehicle Listing: объявлен вывод 12.06.2025, снят из отчётов 09.09.2025.",
    "Practice": "Practice problem: уведомление 05.11.2025, документация снята 06.01.2026.",
}

COMMON_PROPS = {
    "@context", "@type", "@id", "@graph", "@language", "@value", "@list", "@set", "@reverse",
    "name", "alternateName", "description", "disambiguatingDescription", "url", "image", "sameAs",
    "identifier", "mainEntityOfPage", "potentialAction", "subjectOf", "additionalType",
    "inLanguage", "keywords", "about", "isPartOf", "hasPart", "author", "creator", "publisher",
    "dateCreated", "datePublished", "dateModified", "license", "copyrightHolder", "copyrightYear",
    "aggregateRating", "review", "offers", "provider", "brand", "logo", "address", "telephone",
    "email", "contactPoint", "founder", "foundingDate", "vatID", "taxID", "legalName",
    "numberOfEmployees", "areaServed", "audience", "thumbnailUrl", "width", "height", "caption",
    "contentUrl", "embedUrl", "uploadDate", "duration", "position", "item", "itemListElement",
    "itemListOrder", "numberOfItems", "mainEntity", "acceptedAnswer", "suggestedAnswer", "text",
    "upvoteCount", "answerCount", "startDate", "endDate", "doorTime", "location", "organizer",
    "performer", "eventStatus", "eventAttendanceMode", "price", "priceCurrency", "availability",
    "itemCondition", "priceValidUntil", "validFrom", "validThrough", "seller", "sku", "gtin",
    "gtin8", "gtin12", "gtin13", "gtin14", "mpn", "category", "hasAdultConsideration", "material",
    "color", "size", "weight", "ratingValue", "bestRating", "worstRating", "ratingCount",
    "reviewCount", "reviewRating", "itemReviewed", "reviewBody", "datePosted", "validThrough",
    "hiringOrganization", "jobLocation", "employmentType", "baseSalary", "title", "occupationalCategory",
    "jobLocationType", "applicantLocationRequirements", "directApply", "recipeIngredient",
    "recipeInstructions", "recipeYield", "cookTime", "prepTime", "totalTime", "nutrition",
    "recipeCategory", "recipeCuisine", "openingHours", "openingHoursSpecification", "priceRange",
    "geo", "latitude", "longitude", "department", "parentOrganization", "subOrganization",
    "applicationCategory", "operatingSystem", "softwareVersion", "jobTitle", "worksFor",
    "knowsAbout", "knowsLanguage", "affiliation", "alumniOf", "birthDate", "nationality",
    "streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry",
    "headline", "articleBody", "articleSection", "wordCount", "speakable", "isAccessibleForFree",
    "hasCourseInstance", "value", "currency", "unitText", "minValue", "maxValue", "query-input",
    "target", "actionPlatform", "result", "step", "tool", "supply", "yield", "estimatedCost",
    "video", "audio", "contentRating", "genre", "creditText", "acquireLicensePage", "pagination",
    "breadcrumb", "primaryImageOfPage", "significantLink", "thumbnail", "photo", "hasMap",
    "additionalProperty", "itemOffered", "shippingDetails", "hasMerchantReturnPolicy",
    "deliveryTime", "availabilityStarts", "availabilityEnds", "paymentAccepted", "currenciesAccepted",
    "slogan", "award", "member", "memberOf", "employee", "founders", "contactType", "availableLanguage",
    "publishingPrinciples", "correctionsPolicy", "ownershipFundingInfo", "ethicsPolicy",
    "diversityPolicy", "actionableFeedbackPolicy", "abstract", "backstory", "dateline",
    "encodingFormat", "transcript", "interactionStatistic", "interactionType", "userInteractionCount",
    "commentCount", "comment", "isFamilyFriendly", "timeRequired", "educationalLevel",
    "educationalUse", "learningResourceType", "applicationSubCategory", "downloadUrl", "installUrl",
    "screenshot", "softwareRequirements", "fileSize", "releaseNotes", "featureList",
    "maximumAttendeeCapacity", "remainingAttendeeCapacity", "offerCount", "lowPrice", "highPrice",
    "deliveryLeadTime", "validForMemberTier", "mainContentOfPage", "specialty", "medicalSpecialty",
}
DATE_PROPS = {"datePublished", "dateModified", "dateCreated", "startDate", "endDate", "doorTime",
              "validFrom", "validThrough", "priceValidUntil", "uploadDate", "datePosted",
              "previousStartDate", "birthDate", "foundingDate", "expires", "availabilityStarts",
              "availabilityEnds"}
URL_PROPS = {"url", "sameAs", "logo", "contentUrl", "embedUrl", "thumbnailUrl", "acquireLicensePage",
             "target", "license"}
NUM_PROPS = {"price", "ratingValue", "bestRating", "worstRating", "ratingCount", "reviewCount",
             "position", "answerCount", "upvoteCount", "numberOfItems", "latitude", "longitude",
             "width", "height", "minValue", "maxValue", "value"}
EMPTY_MARKERS = {"", "null", "none", "n/a", "na", "undefined", "nan", "-", "—", "не указано",
                 "не указан", "не указана", "tbd", "0000-00-00"}
_ISO_DT = re.compile(
    r"^\d{4}(-\d{2}(-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?)?)?$")
_DURATION = re.compile(r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?!$)(\d+H)?(\d+M)?(\d+(\.\d+)?S)?)?$")
_TYPE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_PROP_NAME = re.compile(r"^[a-z][A-Za-z0-9]*(-input)?$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_MONEY_CHARS = re.compile(r"[^\d.,\-+eE\s]")

class Rows:
    """Check rows. Unlike page_facts, a row repeats per entity: the entity path is in `entity`."""

    def __init__(self):
        self.rows: list[dict] = []
        self.capped = False

    def add(self, cid: str, status: str, observation: str, *, entity: str | None = None,
            evidence=None, value=None, severity: str | None = None, note: str | None = None):
        if len(self.rows) >= MAX_ROWS:
            self.capped = True
            return None
        group, title, how, sev, source, registry = CHECK_META[cid]
        row = {"id": cid, "group": group, "title": title, "status": status, "observation": observation,
               "severity": "info" if status in ("pass", "info", "skip") else (severity or sev),
               "source": source, "registry": registry}
        if entity:
            row["entity"] = entity
        if evidence is not None:
            row["evidence"] = http_safe.escape_snippet(str(evidence), 200)
        if value is not None:
            row["value"] = value
        if note:
            row["note"] = note
        self.rows.append(row)
        return row


def check_rows() -> list[dict]:
    """The contract: every check this script can report. Compared with registry.json by id."""
    return [{"id": cid, "group": g, "title": t, "how": how, "severity": sev, "source": src,
             "registry": reg}
            for cid, (g, t, how, sev, src, reg) in sorted(CHECK_META.items())]


# ------------------------------------------------------------------------------------- traversal

def _types_of(node: dict) -> list[str]:
    t = node.get("@type")
    if isinstance(t, str):
        return [t.split("/")[-1].split(":")[-1]]
    if isinstance(t, list):
        return [x.split("/")[-1].split(":")[-1] for x in t if isinstance(x, str)]
    return []


def _walk(node, path: str, out: list, depth: int = 0, max_depth: list | None = None,
          via: str | None = None):
    """Every dict that looks like a schema.org node, with its path and `via` — the property through
    which it was reached. `via` отличает самостоятельную сущность от значения роли (`publisher`
    внутри Article). Depth is recorded, not followed past MAX_DEPTH."""
    if max_depth is not None:
        max_depth[0] = max(max_depth[0], depth)
    if depth > MAX_DEPTH or len(out) >= MAX_ENTITIES:
        return
    if isinstance(node, dict):
        if node.get("@graph") is not None and not _types_of(node):
            _walk(node["@graph"], path + "/@graph", out, depth + 1, max_depth, via)
            for k, v in node.items():
                if k != "@graph" and isinstance(v, (dict, list)):
                    _walk(v, f"{path}/{k}", out, depth + 1, max_depth, k)
            return
        out.append({"path": path, "node": node, "types": _types_of(node), "depth": depth,
                    "via": via})
        for k, v in node.items():
            if isinstance(v, (dict, list)) and not k.startswith("@"):
                _walk(v, f"{path}/{k}", out, depth + 1, max_depth, k)
            elif k == "@graph" and isinstance(v, (dict, list)):
                _walk(v, f"{path}/@graph", out, depth + 1, max_depth, via)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]", out, depth + 1, max_depth, via)


def _as_list(value):
    return value if isinstance(value, list) else [value]


def _context_ok(ctx) -> bool:
    if isinstance(ctx, str):
        return "schema.org" in ctx.lower()
    if isinstance(ctx, list):
        return any(_context_ok(c) for c in ctx)
    if isinstance(ctx, dict):
        return any(_context_ok(v) for v in ctx.values()) or "schema.org" in json.dumps(ctx).lower()
    return False


def _flat_text(value, out: list, depth: int = 0):
    if depth > 6 or len(out) > 200:
        return
    if isinstance(value, (str, int, float)):
        out.append(str(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            if not k.startswith("@") or k == "@value":
                _flat_text(v, out, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _flat_text(v, out, depth + 1)

def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().replace(" ", "").replace(" ", "")
        if raw.count(",") == 1 and "." not in raw:
            raw = raw.replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None
    return None

# --------------------------------------------------------- проверка полей типов (markup.req_*)

# ------------------------------------------------- свойства, которыми сущность названа в чужой роли
# Узел под этими свойствами — не сущность сайта, а значение роли: `publisher` внутри Article у
# Google в примерах так и выглядит — {Organization, name, logo}. Судить такой обрубок по правилам
# самостоятельной Organization значит выдавать три находки из одной причины (QA 30.10.2026, P1).
ROLE_PROPS = {
    "author", "publisher", "provider", "creator", "hiringOrganization", "seller", "brand",
    "organizer", "performer", "funder", "copyrightHolder", "sourceOrganization",
    "parentOrganization", "subOrganization", "memberOf", "affiliation", "worksFor", "founder",
    "employee", "member", "sponsor", "translator", "editor", "contributor", "manufacturer",
    "vendor", "broker", "customer", "recipient", "accountablePerson", "director", "actor",
    "musicBy", "producer", "character", "itemReviewed", "about", "mentions", "citation",
}
# вложенные Review и AggregateRating: документация Google не требует у них itemReviewed
NESTED_RATING_VIA = {"review", "aggregateRating", "reviews"}


def _present(node: dict, prop: str) -> bool:
    if prop == "@id":
        return bool(str(node.get("@id") or "").strip())
    v = node.get(prop)
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip().lower() not in EMPTY_MARKERS
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def _sub_present(value, subprop: str) -> bool:
    for v in _as_list(value):
        if isinstance(v, dict) and _present(v, subprop):
            return True
    return False


def _deep_nodes(value) -> list:
    return [v for v in _as_list(value) if isinstance(v, dict)]


def _special(key: str, node: dict, via: str | None = None) -> list[str]:
    """Returns the list of what is missing, in words. Empty list = the rule is satisfied."""
    if key == "breadcrumb":
        items = _deep_nodes(node.get("itemListElement"))
        if not items:
            return ["itemListElement с ListItem"]
        miss = []
        no_pos = [i + 1 for i, x in enumerate(items) if _number(x.get("position")) is None]
        no_name = [i + 1 for i, x in enumerate(items)
                   if not (_present(x, "name") or _sub_present(x.get("item"), "name"))]
        no_item = [i + 1 for i, x in enumerate(items[:-1]) if not _present(x, "item")]
        positions = [_number(x.get("position")) for x in items]
        if no_pos:
            miss.append(f"position у пунктов {no_pos}")
        if no_name:
            miss.append(f"name у пунктов {no_name}")
        if no_item:
            miss.append(f"item у пунктов {no_item} (у последнего он не нужен)")
        if not no_pos and [int(p) for p in positions] != list(range(1, len(items) + 1)):
            miss.append(f"непрерывная нумерация с 1 (сейчас {[int(p) for p in positions]})")
        return miss
    if key == "itemlist":
        items = _deep_nodes(node.get("itemListElement"))
        if not items:
            return ["itemListElement с ListItem"]
        miss = []
        no_pos = sum(1 for x in items if _number(x.get("position")) is None)
        no_url = sum(1 for x in items
                     if not (_present(x, "url")
                             or (_present(x, "item") and _sub_present(x.get("item"), "name")
                                 and _sub_present(x.get("item"), "url"))))
        if no_pos:
            miss.append(f"position у {_qty(no_pos, 'пункта', 'пунктов', 'пунктов')}")
        if no_url:
            miss.append("url или item с item.name и item.url у "
                        f"{_qty(no_url, 'пункта', 'пунктов', 'пунктов')}")
        return miss
    if key in ("question_page_qa", "question_page_faq"):
        qs = _deep_nodes(node.get("mainEntity"))
        if not qs:
            return ["mainEntity с Question"]
        miss = []
        no_name = sum(1 for q in qs if not _present(q, "name"))
        no_ans = 0
        for q in qs:
            ans = q.get("acceptedAnswer") or q.get("suggestedAnswer")
            if not _sub_present(ans, "text"):
                no_ans += 1
        if no_name:
            miss.append(f"name у {_qty(no_name, 'вопроса', 'вопросов', 'вопросов')}")
        if no_ans:
            miss.append("acceptedAnswer/suggestedAnswer с text у "
                        f"{_qty(no_ans, 'вопроса', 'вопросов', 'вопросов')}")
        if key == "question_page_qa":
            no_count = sum(1 for q in qs if _number(q.get("answerCount")) is None)
            if no_count:
                miss.append(f"answerCount у {_qty(no_count, 'вопроса', 'вопросов', 'вопросов')}")
        return miss
    if key == "review":
        types = _types_of(node)
        miss = []
        nested = (via or "") in NESTED_RATING_VIA
        if "Review" in types:
            if not _sub_present(node.get("reviewRating"), "ratingValue"):
                miss.append("reviewRating с ratingValue")
            if not _present(node, "author"):
                miss.append("author")
        if "AggregateRating" in types:
            if not _present(node, "ratingValue"):
                miss.append("ratingValue")
            if not (_present(node, "ratingCount") or _present(node, "reviewCount")):
                miss.append("ratingCount или reviewCount")
        if not nested and not _present(node, "itemReviewed"):
            miss.append("itemReviewed (у невложенного отзыва)")
        return miss
    if key == "event_location":
        locs = _deep_nodes(node.get("location"))
        if not locs and not _present(node, "location"):
            return ["location"]
        for loc in locs:
            t = set(_types_of(loc))
            if "VirtualLocation" in t and _present(loc, "url"):
                return []
            if _present(loc, "address"):
                return []
        return ["location с address (у онлайн-события — VirtualLocation с url)"]
    if key == "job_location":
        if _present(node, "jobLocation") or _present(node, "applicantLocationRequirements"):
            return []
        jlt = node.get("jobLocationType")
        if isinstance(jlt, str) and jlt.strip().upper() == "TELECOMMUTE":
            return []
        return ["jobLocation (не нужен при applicantLocationRequirements; "
                "у полностью удалённой работы — jobLocationType=TELECOMMUTE)"]
    if key == "person":
        types = _types_of(node)
        if "ProfilePage" in types:
            persons = _deep_nodes(node.get("mainEntity"))
            if not any("Person" in _types_of(p) or "Organization" in _types_of(p) for p in persons):
                return ["mainEntity с Person"]
            if not any(_present(p, "name") for p in persons):
                return ["name у Person в mainEntity"]
            return []
        return [] if _present(node, "name") else ["name"]
    if key == "offer_price":
        miss = []
        offers = _deep_nodes(node.get("offers"))
        if not offers:
            return []
        for off in offers:
            if "AggregateOffer" in _types_of(off):
                continue
            spec = _deep_nodes(off.get("priceSpecification"))
            price = _number(off.get("price"))
            if price is None:
                price = next((_number(x.get("price")) for x in spec
                              if _number(x.get("price")) is not None), None)
            if price is None:
                miss.append("price числом в Offer или в priceSpecification")
            elif price <= 0:
                miss.append("price больше нуля в Offer")
            cur = off.get("priceCurrency") or next(
                (x.get("priceCurrency") for x in spec if x.get("priceCurrency")), None)
            if not (isinstance(cur, str) and _CURRENCY.match(cur.strip())):
                miss.append("priceCurrency по ISO 4217 в Offer или в priceSpecification")
        return sorted(set(miss))
    if key == "app_price":
        for off in _deep_nodes(node.get("offers")):
            if _number(off.get("price")) is not None:
                return []
        if _number(node.get("price")) is not None:
            return []
        return ["offers.price (для бесплатного приложения — 0)"]
    if key == "speakable":
        for sp in _deep_nodes(node.get("speakable")):
            if _present(sp, "cssSelector") or _present(sp, "xPath"):
                return []
        return ["speakable: cssSelector или xPath"]
    if key == "paywall_part":
        for part in _deep_nodes(node.get("hasPart")):
            if _present(part, "cssSelector"):
                return []
        return ["hasPart с cssSelector закрытой части"]
    return []


def _rule_applies(rule: dict, node: dict, types: list, via: str | None) -> bool:
    if via in ROLE_PROPS and not (rule["id"] == "markup.req_review"
                                  and {"Review", "AggregateRating"} & set(types)):
        return False          # узел в чужой роли — не самостоятельная сущность (P1)
    tset = set(types)
    if rule.get("skip_types") and tset & rule["skip_types"]:
        return False
    hit = bool(tset & rule["types"])
    if not hit and rule.get("types_suffix"):
        hit = any(t.endswith(rule["types_suffix"]) for t in types)
    when = rule.get("when")
    if when == "has_offers":
        return hit and _present(node, "offers")
    if when == "has_searchaction":
        return hit and any("SearchAction" in _types_of(a)
                           for a in _deep_nodes(node.get("potentialAction")))
    if when == "claims_license":
        return hit and any(_present(node, p) for p in ("license", "acquireLicensePage", "creditText",
                                                       "copyrightNotice"))
    if when == "has_speakable":
        return _present(node, "speakable")
    if when == "has_paywall":
        return "isAccessibleForFree" in node
    return hit


def _missing(entries, node: dict, via: str | None) -> list[str]:
    out: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            if not _present(node, entry):
                out.append(entry)
        elif entry[0] == "any":
            if not any(_present(node, p) for p in entry[1]):
                out.append("одно из: " + ", ".join(entry[1]))
        elif entry[0] == "deep":
            if not _present(node, entry[1]):
                out.append(entry[1])
            elif not _sub_present(node.get(entry[1]), entry[2]):
                out.append(f"{entry[1]}.{entry[2]}")
        elif entry[0] == "special":
            out.extend(_special(entry[1], node, via))
    return out


def _required_checks(rows: Rows, node: dict, types: list, label: str, via: str | None = None):
    for rule in REQ_RULES:
        if not _rule_applies(rule, node, types, via):
            continue
        hard = rule.get("doc_required", True)
        missing = _missing(rule["required"], node, via) if hard else []
        scope = node
        if rule.get("recommended_in"):
            inner = _deep_nodes(node.get(rule["recommended_in"]))
            scope = inner[0] if inner else {}
        skip: set = set()
        for t, names in (rule.get("recommended_skip") or {}).items():
            if t in types:
                skip |= set(names)
        soft = [p for p in _missing(rule.get("recommended", []), scope, via) if p not in skip]
        note = rule.get("note")
        if rule.get("retired"):
            rows.add(rule["id"], "info", f"{rule['title']}: разметка есть, требований к ней у Google "
                                         f"нет", entity=label, note=note)
            continue
        if missing:
            rows.add(rule["id"], "fail",
                     f"{rule['title']}: документация Google требует, на странице нет — "
                     + "; ".join(missing), entity=label,
                     value={"missing_required": missing, "missing_recommended": soft}, note=note)
        elif soft and not hard:
            rows.add(rule["id"], "warn",
                     f"{rule['title']}: Google перечисляет как рекомендуемые, на странице нет — "
                     + ", ".join(soft), entity=label, severity="low",
                     value={"missing_recommended": soft},
                     note=(note + ". " if note else "")
                     + "Раздела Required у этого типа в документации Google нет: отсутствие "
                       "свойства не нарушает требования")
        elif soft:
            rows.add(rule["id"], "warn",
                     f"{rule['title']}: документация Google требует всё, что нужно; из "
                     f"рекомендуемых нет — " + ", ".join(soft), entity=label, severity="low",
                     value={"missing_recommended": soft},
                     note=(note + ". " if note else "")
                     + "Рекомендуемые свойства — не требование: без них сущность беднее, "
                       "но ошибки нет")
        elif hard:
            rows.add(rule["id"], "pass",
                     f"{rule['title']}: требуемые и рекомендуемые свойства на месте", entity=label,
                     note=note)
        else:
            rows.add(rule["id"], "pass",
                     f"{rule['title']}: все свойства, которые Google рекомендует, на месте",
                     entity=label, note=note)


# ------------------------------------------------------------------------------- проверка сущности

def check_entity(rows: Rows, ent: dict, ids_seen: Counter, refs: list, canonical: str | None):
    node, path, types = ent["node"], ent["path"], ent["types"]
    via = ent.get("via")
    label = (types[0] if types else "?") + " @ " + path
    if not types:
        oid = node.get("@id")
        if isinstance(oid, str) and oid.strip() and len(node) == 1:
            refs.append((oid.strip(), path))      # {"@id": …} — ссылка на узел, а не сущность
            return
        if set(node) - {"@id"}:
            rows.add("markup.jsonld_type", "fail",
                     "У сущности нет @type: поисковик не поймёт, что размечено", entity=path,
                     evidence=", ".join(sorted(node)[:6]))
        return
    bad_names = [t for t in types if not _TYPE_NAME.match(t)]
    if bad_names:
        rows.add("markup.jsonld_type", "fail",
                 "Имя типа не похоже на тип schema.org (UpperCamelCase): " + ", ".join(bad_names),
                 entity=label, value=bad_names)
    props = [k for k in node if not k.startswith("@")]

    # --- словарь свойств
    bad_case = [k for k in props if not _PROP_NAME.match(k)]
    unknown = [k for k in props if k not in COMMON_PROPS and _PROP_NAME.match(k)]
    if bad_case or unknown:
        rows.add("markup.schemaorg_vocab", "warn" if bad_case else "info",
                 ("Свойства записаны не как в schema.org: " + ", ".join(bad_case[:6]) if bad_case else "")
                 + ("; " if bad_case and unknown else "")
                 + ("нет в нашем списке известных: " + ", ".join(sorted(unknown)[:8]) if unknown else ""),
                 entity=label, value={"wrong_case": bad_case[:10], "unknown": sorted(unknown)[:15]},
                 note="Список известных свойств в скрипте не полон — сверьте имена со schema.org")

    # --- плейсхолдеры и пустые значения
    empty = []
    for k in props:
        for v in _as_list(node[k]):
            if v is None or (isinstance(v, str) and v.strip().lower() in EMPTY_MARKERS) \
                    or (isinstance(v, (list, dict)) and not v):
                empty.append(k)
                break
    if empty:
        rows.add("markup.placeholders", "fail",
                 "Пустые значения или плейсхолдеры у свойств: " + ", ".join(sorted(set(empty))[:8]),
                 entity=label, value=sorted(set(empty))[:15])

    # --- форматы значений
    bad_dates, rel_urls, bad_nums = [], [], []
    for k in props:
        for v in _as_list(node[k]):
            if not isinstance(v, str) or not v.strip():
                continue
            if k in DATE_PROPS and not (_ISO_DT.match(v.strip()) or _DURATION.match(v.strip())):
                bad_dates.append(f"{k}={v.strip()[:30]}")
            if k in URL_PROPS and not re.match(r"^https?://", v.strip(), re.I):
                rel_urls.append(f"{k}={v.strip()[:40]}")
            if k in NUM_PROPS and _MONEY_CHARS.search(v.strip()):
                bad_nums.append(f"{k}={v.strip()[:20]}")
    if bad_dates:
        rows.add("markup.date_format", "fail", "Даты не по ISO 8601: " + "; ".join(bad_dates[:5]),
                 entity=label, value=bad_dates[:10])
    if rel_urls:
        rows.add("markup.relative_urls", "fail",
                 "Адреса в разметке не абсолютные: " + "; ".join(rel_urls[:5]), entity=label,
                 value=rel_urls[:10])

    # --- цена и валюта
    types_set = set(types)
    if "Offer" in types_set or "AggregateOffer" in types_set or node.get("price") is not None:
        miss = []
        price = node.get("price") if node.get("price") is not None else node.get("lowPrice")
        if price is not None:
            val = _number(price)
            if val is None:
                miss.append(f"price не читается числом: {str(price)[:30]}")
            elif val <= 0:
                miss.append(f"price не больше нуля: {val}")
        cur = node.get("priceCurrency")
        if cur is not None and not (isinstance(cur, str) and _CURRENCY.match(str(cur).strip())):
            miss.append(f"priceCurrency не по ISO 4217: {str(cur)[:12]}")
        if bad_nums:
            miss.extend(bad_nums[:3])
        rows.add("markup.price_format", "fail" if miss else "pass",
                 "; ".join(miss) if miss else "Цена числом, валюта кодом ISO 4217", entity=label)
    elif bad_nums:
        rows.add("markup.price_format", "fail",
                 "Числовые свойства записаны строкой со лишними знаками: " + "; ".join(bad_nums[:5]),
                 entity=label, value=bad_nums[:10])

    # --- отзывы о себе
    if (types_set & {"Organization", "LocalBusiness"} or any(
            t.endswith(("Business", "Store")) for t in types)) and via not in ROLE_PROPS:
        if node.get("review") or node.get("aggregateRating"):
            rows.add("markup.sd_self_serving", "fail",
                     "Отзывы о себе: страница, где сущность сама контролирует отзывы, звёзд не получает",
                     entity=label, note="facts-2026 §6, обновление 08.09.2026")

    # --- url против canonical
    if canonical:
        own = node.get("url")
        if isinstance(own, str) and own.strip() and via not in ROLE_PROPS \
                and types_set & {"WebPage", "Article", "NewsArticle",
                                                                 "BlogPosting", "Product", "Event",
                                                                 "JobPosting", "Recipe", "ProfilePage"}:
            same = page_facts._same_url(own.strip(), canonical)
            rows.add("markup.url_vs_canonical", "pass" if same else "warn",
                     "url разметки совпадает с canonical" if same
                     else "url разметки и canonical указывают на разные адреса", entity=label,
                     evidence=f"url={own.strip()} canonical={canonical}")

    # --- AggregateOffer на странице продажи
    if "Product" in types_set and node.get("offers"):
        agg = [o for o in _deep_nodes(node.get("offers")) if "AggregateOffer" in _types_of(o)]
        rows.add("commerce.aggregate_offer_misuse", "fail" if agg else "pass",
                 "AggregateOffer в Product с offers: merchant listings его не поддерживают"
                 if agg else "AggregateOffer на странице продажи не используется", entity=label,
                 note="В product snippets AggregateOffer поддержан (facts-2026 §6)" if agg else None)

    # --- поля типов по документации Google
    _required_checks(rows, node, types, label, via)

    # --- @id
    oid = node.get("@id")
    if isinstance(oid, str) and oid.strip():
        if len(node) <= 1:
            refs.append((oid.strip(), path))
        else:
            ids_seen[oid.strip()] += 1


# Типографика: в разметке и в видимом тексте одно и то же слово часто набрано разными
# символами — &nbsp; против пробела, неразрывный дефис против обычного, «ёлочки» против
# кавычек. Без приведения к одному виду сравнение даёт ложные «значения не видны».
_DROP_CHARS = str.maketrans(dict.fromkeys("­​‌‍⁠﻿", ""))
_FOLD_CHARS = str.maketrans({
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    "−": "-", "«": '"', "»": '"', "“": '"', "”": '"', "„": '"',
    "‘": "'", "’": "'", "′": "'", "″": '"', "…": "...",
})


def _plain(text) -> str:
    """Один вид для сравнения: без невидимых символов, с обычными дефисами и кавычками."""
    folded = str(text).translate(_DROP_CHARS).translate(_FOLD_CHARS)
    return re.sub(r"\s+", " ", folded).strip().lower()


def _visible_values(rows: Rows, entities: list, visible: str, hydration: dict | None = None,
                    other_formats: list | None = None):
    """facts-2026 §6 / sd-policies: размечать только видимое. Эвристика по числам и названиям."""
    if not entities:
        # В сущности разбирается только JSON-LD. Раньше пустой список давал «норма»:
        # страница с ценой и рейтингом в микроданных получала зелёную строку, хотя
        # ни одного значения никто не смотрел. Непроверенное не считается исправным.
        formats = sorted({str(f) for f in (other_formats or []) if f})
        rows.add("markup.visible_values", "skip",
                 "Разметка есть только в " + ", ".join(formats)
                 + ": в сущности разбирается JSON-LD, значения не сверялись" if formats
                 else "Сверять нечего: JSON-LD на странице нет",
                 note="Это «нет данных», а не «у сайта всё хорошо»" if formats else None)
        return
    if hydration and hydration.get("suspected"):
        rows.add("markup.visible_values", "skip",
                 "Значения подставляет браузер из состояния в скрипте ("
                 + ", ".join(hydration.get("markers") or ["встроенное состояние"])
                 + f", {_qty(hydration.get('inline_js_bytes') or 0, 'байт', 'байта', 'байт')} "
                   f"скрипта на "
                   f"{_qty(hydration.get('words_visible') or 0, 'слово', 'слова', 'слов')} "
                   f"текста): без рендера сверить с видимым "
                   "текстом нельзя",
                 value={k: hydration.get(k) for k in ("markers", "inline_js_bytes",
                                                       "words_visible", "bytes_per_word")},
                 note="Это «нет данных», а не «у сайта всё хорошо»: проверьте в браузере")
        return
    norm = _plain(visible)
    if not norm:
        rows.add("markup.visible_values", "skip", "Видимого текста нет (на входе JSON, не страница)")
        return
    # «4 578 ₽» на странице и 4578 в разметке — одно и то же число. Для поиска чисел
    # держим второй текст, в котором разделители разрядов между цифрами убраны.
    norm_digits = re.sub(r"(?<=\d)[ ']+(?=\d)", "", norm)
    missing = []
    for ent in entities:
        node, types = ent["node"], ent["types"]
        label = (types[0] if types else "?") + " @ " + ent["path"]
        for key in ("price", "ratingValue"):
            v = _number(node.get(key))
            if v is None:
                continue
            shapes = {f"{v:g}", f"{v:.2f}".rstrip("0").rstrip(".")}
            if v == int(v):
                shapes.add(str(int(v)))
            shapes |= {s.replace(".", ",") for s in shapes if s}
            if not any(s and (s in norm or s in norm_digits) for s in shapes):
                missing.append({"entity": label, "prop": key, "value": v})
        for key in ("name", "headline"):
            val = node.get(key)
            if isinstance(val, str) and len(val.strip()) >= 8 and types and types[0] in (
                    "Product", "Event", "Recipe", "JobPosting", "SoftwareApplication", "Article",
                    "NewsArticle", "BlogPosting"):
                if _plain(val) not in norm:
                    missing.append({"entity": label, "prop": key, "value": val.strip()[:60]})
    rows.add("markup.visible_values", "fail" if missing else "pass",
             f"Значений разметки не нашлось в видимом тексте: {len(missing)}" if missing
             else "Проверенные значения разметки есть в видимом тексте",
             value=missing[:10] or None,
             note="Эвристика: текст сравнивается без форматирования, проверьте глазами")


# ------------------------------------------------------------------------------------- the report

def check_structured_data(*, jsonld_blocks: list, microdata_types: list | None = None,
                          rdfa_types: list | None = None, visible_text: str = "",
                          url: str | None = None, canonical: str | None = None,
                          hydration: dict | None = None) -> dict:
    """jsonld_blocks — блоки в формате page_facts._parse_jsonld (parse_ok, data, line, types)."""
    rows = Rows()
    microdata_types = [t.split("/")[-1] for t in (microdata_types or [])]
    rdfa_types = list(rdfa_types or [])
    any_markup = bool(jsonld_blocks or microdata_types or rdfa_types)
    rows.add("markup.jsonld_present", "info" if any_markup else "fail",
             f"JSON-LD блоков {len(jsonld_blocks)}, типов microdata {len(set(microdata_types))}, "
             f"RDFa {len(set(rdfa_types))}" if any_markup
             else "Структурированной разметки на странице не найдено",
             value={"jsonld_blocks": len(jsonld_blocks), "microdata": sorted(set(microdata_types)),
                    "rdfa": sorted(set(rdfa_types))},
             severity="medium")
    formats = [n for n, on in (("JSON-LD", bool(jsonld_blocks)), ("microdata", bool(microdata_types)),
                               ("RDFa", bool(rdfa_types))) if on]
    rows.add("markup.format_preference", "info" if formats else "skip",
             "Форматы на странице: " + ", ".join(formats) if formats else "Разметки нет",
             value=formats,
             note="Google рекомендует JSON-LD; Яндекс часть типов берёт только из микроданных "
                  "(facts-2026 §6, §13)" if formats else None)
    broken = [b for b in jsonld_blocks if not b.get("parse_ok")]
    rows.add("markup.jsonld_parses", "fail" if broken else ("pass" if jsonld_blocks else "skip"),
             f"Не разбираются блоки JSON-LD: {len(broken)} из {len(jsonld_blocks)}" if broken
             else ("Единственный блок JSON-LD разбирается" if len(jsonld_blocks) == 1
                   else (f"Все {_qty(len(jsonld_blocks), 'блок', 'блока', 'блоков')} "
                         f"JSON-LD разбираются" if jsonld_blocks
                         else "Блоков JSON-LD нет")),
             value=[{"line": b["line"], "error": b.get("error")} for b in broken[:10]] or None)

    entities: list[dict] = []
    deepest = [0]
    ctx_bad, ctx_total = [], 0
    for i, b in enumerate(jsonld_blocks):
        data = b.get("data")
        if not b.get("parse_ok") or data is None:
            continue
        tops = _as_list(data)
        for j, top in enumerate(tops):
            path = f"block{i}" + (f"[{j}]" if len(tops) > 1 else "")
            if isinstance(top, dict):
                ctx_total += 1
                if "@context" not in top:
                    ctx_bad.append(f"{path}: нет @context (строка {b['line']})")
                elif not _context_ok(top.get("@context")):
                    ctx_bad.append(f"{path}: @context не на schema.org")
            found: list[dict] = []
            _walk(top, path, found, 0, deepest)
            for ent in found:
                ent["line"] = b["line"]
            entities.extend(found)
    if not ctx_total:
        rows.add("markup.jsonld_context", "skip", "Блоков JSON-LD нет")
    else:
        rows.add("markup.jsonld_context", "fail" if ctx_bad else "pass",
                 "; ".join(ctx_bad[:5]) if ctx_bad
                 else ("@context на schema.org в единственном блоке" if ctx_total == 1
                       else f"@context на schema.org во всех {ctx_total} блоках"),
                 value=ctx_bad[:10] or None)

    ids_seen: Counter = Counter()
    refs: list = []
    typed = [e for e in entities[:MAX_ENTITIES] if e["types"]]
    for ent in entities[:MAX_ENTITIES]:
        check_entity(rows, ent, ids_seen, refs, canonical)
    if typed and not any(r["id"] == "markup.jsonld_type" for r in rows.rows):
        rows.add("markup.jsonld_type", "pass",
                 "У единственной сущности есть @type" if len(typed) == 1
                 else f"У всех {_qty(len(typed), 'сущности', 'сущностей', 'сущностей')} есть @type")
    for cid, msg in (("markup.placeholders", "Пустых значений и плейсхолдеров нет"),
                     ("markup.date_format", "Все даты по ISO 8601"),
                     ("markup.relative_urls", "Все адреса в разметке абсолютные"),
                     ("markup.schemaorg_vocab", "Все имена свойств из нашего списка известных"),
                     ("markup.sd_self_serving", "Отзывов о себе в разметке нет")):
        if typed and not any(r["id"] == cid for r in rows.rows):
            rows.add(cid, "pass", msg)
    dup_ids = {k: v for k, v in ids_seen.items() if v > 1}
    rows.add("markup.id_duplicate", "fail" if dup_ids else ("pass" if ids_seen else "skip"),
             f"Повторяются @id: {len(dup_ids)}" if dup_ids
             else ("Единственный @id уникален" if len(ids_seen) == 1
                   else (f"Все {len(ids_seen)} @id уникальны" if ids_seen else "@id не используются")),
             value=sorted(dup_ids)[:10] or None)
    dangling = sorted({r for r, _ in refs if r not in ids_seen})
    rows.add("markup.id_dangling", "warn" if dangling else ("pass" if refs else "skip"),
             f"Ссылок на @id без узла в этом документе: {len(dangling)}" if dangling
             else ("Все ссылки на @id находят узел" if refs else "Ссылок на @id нет"),
             value=dangling[:10] or None,
             note="Узел может лежать на другой странице — это допустимо" if dangling else None)
    type_counts = Counter(t for ent in entities for t in ent["types"])
    repeated = {t: n for t, n in type_counts.items()
                if n > 1 and t in ("Organization", "WebSite", "WebPage", "BreadcrumbList",
                                   "LocalBusiness")}
    rows.add("markup.duplicate_types", "info" if repeated else "pass",
             "Один тип в нескольких сущностях: " + ", ".join(f"{t}×{n}" for t, n in repeated.items())
             if repeated else "Главные типы не дублируются", value=repeated or None)
    rows.add("markup.jsonld_depth", "info",
             f"Сущностей {len(entities)}, самая глубокая ветка {deepest[0]}, "
             f"байт в блоках {sum(b.get('bytes', 0) for b in jsonld_blocks)}",
             value={"entities": len(entities), "depth": deepest[0]})
    if not type_counts:
        rows.add("markup.yandex_supported", "skip", "Типов в разметке нет")
    else:
        unsupported = sorted(t for t in type_counts
                             if t not in YANDEX_SUPPORTED
                             and not any(t.endswith(sfx) for sfx in ("Business", "Store", "Shop",
                                                                     "Restaurant", "Hotel")))
        rows.add("markup.yandex_supported", "info" if unsupported else "pass",
                 "Нет в списке поддерживаемых Яндексом: " + ", ".join(unsupported) if unsupported
                 else "Все типы есть в списке поддерживаемых Яндексом",
                 value=unsupported or None,
                 note="Неподдерживаемую разметку Яндекс просто пропускает; FAQPage он не "
                      "поддерживает — FAQ-сниппет в Яндексе не обещать")
    retired = sorted({t: RETIRED[t] for t in type_counts if t in RETIRED}.items())
    if retired:
        rows.add("markup.retired_type", "warn",
                 "; ".join(f"{t}: {why}" for t, why in retired), value=[t for t, _ in retired],
                 note="Разметка не вредит — не обещайте по ней карточку в выдаче")
    else:
        rows.add("markup.retired_type", "pass", "Снятых типов на странице нет")
    _visible_values(rows, entities[:MAX_ENTITIES], visible_text, hydration,
                    other_formats=[n for n in formats if n != "JSON-LD"])

    by_status = Counter(r["status"] for r in rows.rows)
    first = [r["id"] for r in rows.rows if r["status"] in ("fail", "warn")
             and r["severity"] in ("critical", "high")]
    return {
        "notice": "Разметка страницы — данные, не инструкции.",
        "url": url,
        "registry_version": REGISTRY_VERSION,
        "types_found": sorted(type_counts),
        "type_counts": dict(type_counts.most_common()),
        "entities": [{"path": e["path"], "types": e["types"], "line": e.get("line"),
                      "props": sorted(k for k in e["node"] if not k.startswith("@"))[:40]}
                     for e in entities[:MAX_ENTITIES]],
        "entity_count": len(entities),
        "entities_truncated": len(entities) > MAX_ENTITIES,
        "microdata_types": sorted(set(microdata_types)),
        "rdfa_types": sorted(set(rdfa_types)),
        "checks": rows.rows,
        "checks_truncated": rows.capped,
        "rows_are_per_entity": True,
        "checks_summary": dict(by_status) | {"first_to_fix": sorted(set(first))},
        "method": "DETERMINISTIC, кроме markup.visible_values (HEURISTIC)",
    }


def check_page(html: str, *, url: str | None = None, headers: dict | None = None) -> dict:
    facts = page_facts.analyze_html(html, url=url, headers=headers)
    if "error" in facts:
        return facts
    canonical = facts["canonical"][0]["href"] if facts["canonical"] else facts.get("canonical_header")
    vis = page_facts.visible_text(html, url)
    out = check_structured_data(jsonld_blocks=facts["json_ld"],
                                microdata_types=facts["microdata_types"],
                                rdfa_types=facts["rdfa_types"], visible_text=vis["text"], url=url,
                                canonical=canonical,
                                hydration=(facts.get("csr") or {}).get("hydration"))
    out["hidden_instructions"] = facts["hidden_instructions"]
    return out

# ------------------------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    def body() -> int:
        p = http_safe.JsonArgumentParser(prog="schema_check.py",
                                         description="Structured data of one page, checked")
        p.add_argument("source", nargs="?", help="HTML file, JSON-LD file or http(s) URL")
        p.add_argument("--base-url", help="page URL for a local file")
        p.add_argument("--list-checks", action="store_true", help="print every check and its source")
        http_safe.add_pace_args(p)
        p.add_argument("--out")
        args = p.parse_args(argv)
        if args.out:
            http_safe.safe_out_path(args.out)
        if args.list_checks:
            rows = check_rows()
            return http_safe.emit({"checks": rows, "count": len(rows),
                                   "note": "Серьёзность — наша по умолчанию; registry.json главнее."},
                                  args.out, {"count": len(rows)})
        if not args.source:
            raise http_safe.CliError("give an HTML/JSON file or a URL", "bad_arguments")
        delay = http_safe.check_delay(args.delay)
        state_dir = http_safe.check_state_dir(args.state_dir)
        if http_safe.is_url(args.source):
            fetcher = http_safe.Fetcher(delay=delay, state_dir=state_dir)
            resp = fetcher.fetch(args.source)
            result = check_page(resp.text(), url=resp.final_url, headers=resp.headers)
            if "error" in result:
                raise http_safe.CliError(result["error"], result.get("code", "parse_failed"))
            result["fetch"] = page_facts.fetch_block(resp, fetcher)
        else:
            data, truncated = http_safe.read_input_file(args.source, page_facts.MAX_HTML_BYTES)
            if args.base_url:
                http_safe.validate_url(args.base_url, allow_local=True)
            text = http_safe.decode_body(data)
            stripped = text.lstrip()
            if args.source.lower().endswith(".json") or stripped[:1] in ("{", "["):
                try:
                    doc = json.loads(text)
                except ValueError as exc:
                    raise http_safe.CliError(f"invalid JSON: {exc}", "bad_input") from None
                block = {"line": 1, "parse_ok": True, "data": doc, "in_head": False,
                         "types": [], "bytes": len(data)}
                result = check_structured_data(jsonld_blocks=[block], url=args.base_url)
            else:
                result = check_page(text, url=args.base_url)
                if "error" in result:
                    raise http_safe.CliError(result["error"], result.get("code", "parse_failed"))
            result["fetch"] = {"path": os.path.abspath(args.source), "truncated": truncated,
                               "bytes": len(data)}
        summary = {"types": result["types_found"], "entities": result["entity_count"],
                   "fail": result["checks_summary"].get("fail", 0),
                   "warn": result["checks_summary"].get("warn", 0),
                   "first_to_fix": result["checks_summary"]["first_to_fix"]}
        return http_safe.emit(result, args.out, summary)

    return http_safe.run_cli(body)


if __name__ == "__main__":
    sys.exit(main())
