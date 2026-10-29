"""Тесты scripts/text_metrics.py. Запуск из папки скила:
python3 -m unittest tests.test_text_metrics
"""
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tm = load("text_metrics")


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = tm.main(argv)
    return rc, json.loads(buf.getvalue())


class TestCounts(unittest.TestCase):
    def test_ru_counts(self):
        r = tm.analyze("Мама мыла раму. Папа читал книгу.")
        self.assertEqual(r["lang"], "ru")
        self.assertEqual(r["counts"]["words"], 6)
        self.assertEqual(r["counts"]["sentences_prose"], 2)
        self.assertEqual(r["counts"]["chars_no_spaces"], len("Мамамылараму.Папачиталкнигу."))
        self.assertEqual(r["status"], "оценка")

    def test_en_detected(self):
        r = tm.analyze("The cat sat on the mat. Dogs were running outside.")
        self.assertEqual(r["lang"], "en")
        self.assertEqual(r["counts"]["sentences_prose"], 2)

    def test_abbreviations_do_not_split(self):
        r = tm.analyze("Выбор большой, т. е. есть из чего выбрать. Второе предложение тут.")
        self.assertEqual(r["counts"]["sentences_prose"], 2)
        r2 = tm.analyze("Цена 5 тыс. руб. за штуку. Дальше текст.")
        self.assertEqual(r2["counts"]["sentences_prose"], 2)

    def test_numbers_are_not_words(self):
        r = tm.analyze("В 2026 году было 12 моделей.")
        self.assertEqual(r["counts"]["words"], 4)
        self.assertEqual(r["counts"]["numbers"], 2)

    def test_code_comments_urls_masked(self):
        text = ("Текст до кода.\n\n```\nслово слово слово\n```\n\n"
                "<!-- скрытый комментарий -->\nСсылка https://example.com/page и `код`.")
        r = tm.analyze(text)
        self.assertEqual(r["masked"]["code_blocks"], 1)
        self.assertEqual(r["masked"]["html_comments"], 1)
        self.assertEqual(r["masked"]["urls"], 1)
        self.assertEqual(r["masked"]["inline_code"], 1)
        self.assertNotIn("слов", [s["stem"] for s in r["stems_top"]])

    def test_html_input(self):
        html = ("<html><head><title>Заголовок вкладки</title><script>var x = 'скрипт';</script>"
                "</head><body><p>Привет, мир.</p><!-- c --><p>Ещё абзац.</p></body></html>")
        r = tm.analyze(html, is_html=True)
        self.assertEqual(r["counts"]["words"], 4)
        self.assertEqual(r["counts"]["paragraphs_prose"], 2)
        self.assertEqual(r["masked"]["html_comments"], 1)

    def test_markdown_structure(self):
        text = "# Заголовок\n\nАбзац один.\n\n- пункт один\n- пункт два\n\n| a | b |\n|---|---|\n| в | г |"
        r = tm.analyze(text)
        self.assertEqual(r["counts"]["headings"], 1)
        self.assertEqual(r["counts"]["list_items"], 2)
        self.assertEqual(r["counts"]["sentences_prose"], 1)


class TestStemsAndKeys(unittest.TestCase):
    def test_ru_stemmer_merges_forms(self):
        self.assertEqual(tm.stem("кошка"), tm.stem("кошкой"))
        self.assertEqual(tm.stem("кошка"), tm.stem("кошки"))
        self.assertEqual(tm.stem("диван"), tm.stem("диванами"))
        self.assertEqual(tm.stem("купить"), tm.stem("купили"))
        self.assertEqual(tm.stem("ёлка"), tm.stem("елки"))

    def test_en_stemmer(self):
        self.assertEqual(tm.stem("studies"), tm.stem("study"))
        self.assertEqual(tm.stem("running"), "run")
        self.assertEqual(tm.stem("class"), "class")

    def test_key_by_stems_with_morphology(self):
        r = tm.analyze("Купить диван можно здесь. Мы купили диваны вчера.", keys=["купить диван"])
        k = r["keys"][0]
        self.assertEqual(k["exact_by_stems"], 2)
        self.assertGreater(k["density_pct"], 0)

    def test_key_does_not_cross_sentences(self):
        r = tm.analyze("Я люблю диван. Угловой стол стоит рядом.", keys=["диван угловой"])
        self.assertEqual(r["keys"][0]["exact_by_stems"], 0)
        self.assertEqual(r["keys"][0]["any_order_window"], 0)

    def test_key_any_order(self):
        r = tm.analyze("Угловой диван стоит в зале.", keys=["диван угловой"])
        self.assertEqual(r["keys"][0]["exact_by_stems"], 0)
        self.assertEqual(r["keys"][0]["any_order_window"], 1)

    def test_key_with_stopword(self):
        r = tm.analyze("Где купить диван в Москве недорого.", keys=["диван в москве"])
        self.assertEqual(r["keys"][0]["exact_by_stems"], 1)

    def test_parse_keys(self):
        self.assertEqual(tm.parse_keys(["a; b", "c"]), ["a", "b", "c"])


class TestEstimates(unittest.TestCase):
    def test_nausea_classic(self):
        r = tm.analyze(" ".join(["окно"] * 9) + ".")
        self.assertEqual(r["nausea"]["classic"], 3.0)
        self.assertEqual(r["nausea"]["top_stem"], tm.stem("окно"))

    def test_water_bounds(self):
        r = tm.analyze("И вот он, и она, и они тоже здесь, но окно открыто.")
        self.assertGreater(r["water"]["stopword_pct"], 50)
        self.assertLessEqual(r["water"]["stopword_pct"], 100)

    def test_empty_text(self):
        r = tm.analyze("")
        self.assertEqual(r["counts"]["words"], 0)
        self.assertEqual(r["water"]["stopword_pct"], 0)

    def test_similar_runs(self):
        self.assertEqual(len(tm.similar_runs([6, 6, 7, 6])), 1)
        self.assertEqual(tm.similar_runs([3, 12, 5, 20]), [])
        self.assertEqual(tm.similar_runs([2, 2, 2]), [])  # короткие не считаем

    def test_cv_reported(self):
        r = tm.analyze("Одно короткое. А это предложение заметно длиннее предыдущего и тянется дальше.")
        self.assertIsNotNone(r["rhythm"]["sentence_words"]["cv"])


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "a.md")
        with open(self.src, "w", encoding="utf-8") as fh:
            fh.write("Текст для проверки. Ещё одно предложение.")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stdout_json(self):
        rc, data = run_cli([self.src, "--keys", "текст"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["tool"], "text_metrics")
        self.assertEqual(data["input"], "a.md")

    def test_out_file(self):
        out = os.path.join(self.tmp.name, "r.json")
        rc, data = run_cli([self.src, "--out", out])
        self.assertEqual(rc, 0)
        self.assertEqual(data["out"], out)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["tool"], "text_metrics")

    def test_out_traversal_without_json_refused(self):
        rc, data = run_cli([self.src, "--out", "../../x"])
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])

    def test_out_symlink_refused(self):
        target = os.path.join(self.tmp.name, "target.json")
        link = os.path.join(self.tmp.name, "link.json")
        open(target, "w").close()
        os.symlink(target, link)
        rc, _ = run_cli([self.src, "--out", link])
        self.assertEqual(rc, 2)

    def test_out_missing_dir_refused(self):
        rc, _ = run_cli([self.src, "--out", os.path.join(self.tmp.name, "no", "r.json")])
        self.assertEqual(rc, 2)

    def test_missing_input(self):
        rc, data = run_cli([os.path.join(self.tmp.name, "nope.md")])
        self.assertEqual(rc, 2)
        self.assertIn("error", data)

    def test_binary_refused(self):
        b = os.path.join(self.tmp.name, "b.bin")
        with open(b, "wb") as fh:
            fh.write(b"\x00\x01\x02text")
        rc, _ = run_cli([b])
        self.assertEqual(rc, 2)


FIXTURES = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


class TestZonesHtml(unittest.TestCase):
    def setUp(self):
        self.z = tm.zones_from_html(fixture("text_ru.html"))

    def test_title_and_description(self):
        self.assertIn("Угловые диваны", self.z["title"]["text"])
        self.assertIn("Купить угловой диван", self.z["description"]["text"])

    def test_headings_split_by_level(self):
        self.assertEqual(self.z["h1"]["text"], "Угловые диваны")
        self.assertEqual(self.z["h2_h6"]["count"], 5)
        self.assertEqual(self.z["_meta"]["headings_by_level"], {"h1": 1, "h2": 3, "h3": 2})

    def test_first_paragraph_prefers_main_and_skips_breadcrumbs(self):
        self.assertEqual(self.z["_meta"]["first_paragraph_source"], "main")
        self.assertTrue(self.z["first_paragraph"]["text"].startswith("Угловой диван закрывает"))
        self.assertNotIn("Главная / Каталог", self.z["first_paragraph"]["text"])

    def test_alt_skips_empty_and_anchors_collected(self):
        self.assertEqual(self.z["alt"]["count"], 2)
        self.assertNotIn("", self.z["alt"]["items"])
        self.assertIn("напишите нам", self.z["anchors"]["items"])
        self.assertEqual(self.z["anchors"]["count"], 5)

    def test_script_and_style_not_in_zones(self):
        joined = " ".join(v["text"] for k, v in self.z.items() if not k.startswith("_"))
        self.assertNotIn("не считается", joined)
        self.assertNotIn("color", joined)

    def test_url_from_canonical(self):
        self.assertIn("uglovye-divany", self.z["url"]["text"])
        self.assertEqual(self.z["_meta"]["url_source"], "link rel=canonical")

    def test_url_argument_wins_over_canonical(self):
        z = tm.zones_from_html(fixture("text_ru.html"), url="https://x.example/other")
        self.assertEqual(z["url"]["text"], "https://x.example/other")
        self.assertEqual(z["_meta"]["url_source"], "аргумент --url")

    def test_unclosed_tags_still_captured(self):
        z = tm.zones_from_html("<h1>Заголовок<p>Абзац из нескольких слов тут")
        self.assertEqual(z["h1"]["text"], "Заголовок")
        self.assertIn("Абзац", z["first_paragraph"]["text"])


class TestZonesMarkdown(unittest.TestCase):
    def setUp(self):
        self.z = tm.zones_from_markdown(fixture("text_ru_before.md"))

    def test_absent_zones_are_empty_not_zero_claims(self):
        self.assertEqual(self.z["title"]["count"], 0)
        self.assertEqual(self.z["url"]["count"], 0)
        self.assertEqual(self.z["_meta"]["absent"], ["title", "description", "url"])

    def test_headings_images_links(self):
        self.assertEqual(self.z["h1"]["count"], 1)
        self.assertIn("Угловой диван в комнате", self.z["alt"]["items"])
        self.assertEqual(self.z["anchors"]["items"], ["в каталоге"])

    def test_image_is_not_counted_as_anchor(self):
        z = tm.zones_from_markdown("![альт тут](/i.jpg)\n\nТекст абзаца здесь.")
        self.assertEqual(z["anchors"]["items"], [])
        self.assertEqual(z["alt"]["items"], ["альт тут"])


class TestUrlTokens(unittest.TestCase):
    def test_hyphens_and_slashes_split(self):
        self.assertEqual(tm.url_tokens("https://a-b.example/katalog/uglovye-divany"),
                         ["a", "b", "example", "katalog", "uglovye", "divany"])

    def test_percent_decoded(self):
        self.assertIn("диваны", tm.url_tokens("https://x.ru/%D0%B4%D0%B8%D0%B2%D0%B0%D0%BD%D1%8B"))

    def test_broken_percent_survives(self):
        self.assertEqual(tm.url_tokens("https://x.ru/%zz"), ["x", "ru", "zz"])

    def test_translit_variants(self):
        self.assertIn("uglov", tm.translit_variants("углов"))
        self.assertTrue({"hleb", "khleb"} <= tm.translit_variants("хлеб"))
        self.assertLessEqual(len(tm.translit_variants("щёлочь" * 4)), tm.TRANSLIT_CAP)


class TestKeyZones(unittest.TestCase):
    def setUp(self):
        self.r = tm.analyze(fixture("text_ru.html"), keys=["угловой диван"], is_html=True)
        self.k = self.r["keys"][0]

    def test_exact_forms_and_morphology_differ(self):
        z = self.k["zones"]
        self.assertEqual(z["h1"]["exact_forms"], 0)      # «Угловые диваны» — другая форма
        self.assertEqual(z["h1"]["morphological"], 1)
        self.assertEqual(z["description"]["exact_forms"], 1)

    def test_every_zone_reported(self):
        self.assertEqual(set(self.k["zones"]), set(tm.ZONE_ORDER))

    def test_zone_density_and_absence(self):
        self.assertEqual(self.k["zones"]["anchors"]["morphological"], 0)
        self.assertFalse(self.k["zones"]["anchors"]["present"])
        self.assertEqual(self.k["zones"]["h1"]["density_pct"], 100.0)

    def test_match_does_not_cross_zone_items(self):
        html = "<body><a href='/a'>угловой</a><a href='/b'>диван</a></body>"
        r = tm.analyze(html, keys=["угловой диван"], is_html=True)
        self.assertEqual(r["keys"][0]["zones"]["anchors"]["morphological"], 0)

    def test_url_translit_match_is_flagged_not_counted(self):
        u = self.k["zones"]["url"]
        self.assertEqual(u["morphological"], 0)
        self.assertEqual(u["translit_stems"], ["углов", "диван"])
        self.assertTrue(u["present"])

    def test_url_cyrillic_counts_as_morphological(self):
        r = tm.analyze("<body><p>Текст страницы тут есть.</p></body>", keys=["угловой диван"],
                       is_html=True, url="https://x.ru/угловые-диваны")
        self.assertEqual(r["keys"][0]["zones"]["url"]["morphological"], 1)

    def test_empty_zone_density_is_null_not_zero(self):
        r = tm.analyze("Текст без разметки совсем.", keys=["диван"])
        self.assertIsNone(r["keys"][0]["zones"]["title"]["density_pct"])
        self.assertEqual(r["keys"][0]["zones"]["title"]["words"], 0)

    def test_cooccurrence_reported_without_lsi_claim(self):
        co = self.k["cooccurrence"]
        self.assertGreater(co["segments_with_key"], 0)
        self.assertIn("LSI", co["note"])
        self.assertTrue(any(x["stem"] for x in co["top"]))


class TestNgrams(unittest.TestCase):
    def test_repeated_phrase_found(self):
        r = tm.analyze("Купите угловой диван сегодня. Угловой диван привезут завтра.")
        two = {x["phrase"]: x["count"] for x in r["ngrams"]["repeated"]["2"]}
        self.assertEqual(two.get("угловой диван"), 2)

    def test_ngrams_do_not_cross_sentences(self):
        r = tm.analyze("Первое слово тут. Слово тут первое снова.")
        self.assertNotIn("тут слово", {x["phrase"] for x in r["ngrams"]["repeated"]["2"]})

    def test_self_repeat_counts_only_three_plus(self):
        r = tm.analyze("Один два три четыре. Один два три пять.")
        self.assertGreater(r["ngrams"]["self_repeat_pct"], 0)
        r2 = tm.analyze("Один два. Два один.")
        self.assertEqual(r2["ngrams"]["self_repeat_pct"], 0)

    def test_distinct_count_is_not_truncated(self):
        parts = [f"сл{chr(0x430 + i)}ка сл{chr(0x430 + i)}ко тут "
                 f"сл{chr(0x430 + i)}ка сл{chr(0x430 + i)}ко." for i in range(20)]
        r = tm.analyze(" ".join(parts))
        self.assertGreater(r["ngrams"]["repeated_distinct"]["2"], 15)
        self.assertLessEqual(len(r["ngrams"]["repeated"]["2"]), 15)

    def test_empty_text(self):
        r = tm.analyze("")
        self.assertEqual(r["ngrams"]["self_repeat_pct"], 0)

    def test_long_text_says_it_was_truncated(self):
        was = tm.NGRAM_MAX_WORDS
        tm.NGRAM_MAX_WORDS = 10
        try:
            r = tm.analyze(". ".join(["одно слово тут и ещё слова"] * 20) + ".")
        finally:
            tm.NGRAM_MAX_WORDS = was
        self.assertIn("truncated", r["ngrams"])
        self.assertIn("предел 10", r["ngrams"]["truncated"])
        self.assertNotIn("truncated", tm.analyze("Короткий текст тут.")["ngrams"])


class TestReadability(unittest.TestCase):
    def test_syllables(self):
        self.assertEqual(tm.syllables_ru("диван"), 2)
        self.assertEqual(tm.syllables_ru("в"), 1)
        self.assertEqual(tm.syllables_en("make"), 1)
        self.assertEqual(tm.syllables_en("coffee"), 2)
        self.assertEqual(tm.syllables_en("little"), 2)

    def test_en_flesch_matches_formula(self):
        r = tm.analyze("The cat sat on the mat.")
        rd = r["readability"]
        self.assertEqual(rd["words"], 6)
        self.assertEqual(rd["syllables"], 6)
        score = {s["name"]: s for s in rd["scores"]}
        self.assertAlmostEqual(score["Flesch Reading Ease"]["value"], 116.1, delta=0.1)
        self.assertIn("206.835", score["Flesch Reading Ease"]["formula"])
        self.assertIn("Flesch", score["Flesch Reading Ease"]["source"])
        self.assertIn("Flesch–Kincaid Grade Level", score)

    def test_ru_adaptation_marked_as_estimate(self):
        r = tm.analyze("Мама мыла раму.")
        scores = r["readability"]["scores"]
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["status"], "оценка")
        self.assertAlmostEqual(scores[0]["value"], 82.7, delta=0.1)
        self.assertIn("206,835", scores[0]["formula"])
        self.assertIn("Оборнева", scores[0]["source"])

    def test_no_english_grade_scale_for_russian(self):
        r = tm.analyze("Мама мыла раму. Папа читал книгу.")
        names = [s["name"] for s in r["readability"]["scores"]]
        self.assertNotIn("Flesch–Kincaid Grade Level", names)

    def test_no_data_without_sentences(self):
        r = tm.analyze("# Только заголовок")
        self.assertIn("unavailable", r["readability"])
        self.assertIsNone(r["readability"]["words_per_sentence"])
        self.assertEqual(r["readability"]["scores"], [])

    def test_no_formula_for_other_languages(self):
        r = tm.analyze("这是一个测试句子。还有第二个句子。")
        self.assertEqual(r["lang"], "unknown")
        self.assertEqual(r["readability"]["scores"], [])
        self.assertIn("нет формулы", r["readability"]["unavailable"])

    def test_search_engines_disclaimer(self):
        r = tm.analyze("Мама мыла раму.")
        self.assertIn("не публиковали", r["readability"]["note"])


class TestClericalAndPassive(unittest.TestCase):
    def test_ru_clerical_markers(self):
        r = tm.analyze("Данный материал подготовлен в целях информирования. "
                       "На сегодняшний день доставка осуществляется ежедневно.")
        found = {m["marker"] for m in r["clerical"]["markers"]}
        self.assertTrue({"данный", "в целях", "на сегодняшний день"} <= found)
        self.assertEqual(r["clerical"]["status"], "оценка")

    def test_en_clerical_markers(self):
        r = tm.analyze("In order to proceed, utilize the form. "
                       "It should be noted that prior to signup we check the email.")
        found = {m["marker"] for m in r["clerical"]["markers"]}
        self.assertTrue({"in order to", "utilize", "prior to"} <= found)

    def test_nominal_nouns_counted_with_caveat(self):
        r = tm.analyze("Решение принято. Обеспечение надежности важно для исполнения.")
        self.assertGreaterEqual(r["clerical"]["nominal_nouns"]["count"], 2)
        self.assertIn("обычная лексика", r["clerical"]["nominal_nouns"]["rule"])

    def test_ru_passive_heuristic(self):
        r = tm.analyze("Рулон был проверен на истирание. Ткань производится в Иваново.")
        self.assertEqual(r["passive"]["sentences_with_marker"], 2)
        self.assertEqual(r["passive"]["status"], "эвристика")

    def test_en_passive_heuristic(self):
        r = tm.analyze("The grounds were weighed on a scale. We filtered the coffee.")
        self.assertEqual(r["passive"]["sentences_with_marker"], 1)

    def test_passive_rule_admits_reflexives(self):
        r = tm.analyze("Мне нравится этот диван очень сильно.")
        self.assertEqual(r["passive"]["sentences_with_marker"], 1)
        self.assertIn("возвратными", r["passive"]["rule"])

    def test_passive_pct_null_without_prose(self):
        r = tm.analyze("# Заголовок")
        self.assertIsNone(r["passive"]["pct"])


class TestHonestyNotes(unittest.TestCase):
    def test_density_and_nausea_not_ranking_factors(self):
        r = tm.analyze("Текст для проверки пометок.", keys=["текст"])
        self.assertIn("не являются факторами ранжирования", r["note"])
        self.assertIn("folklore.md", r["note"])
        self.assertEqual(r["status"], "оценка")

    def test_nausea_formulas_are_spelled_out(self):
        r = tm.analyze("Окно окно окно окно.")
        self.assertIn("√", r["nausea"]["classic_formula"])
        self.assertIn("%", r["nausea"]["academic_formula"])
        self.assertIn("оценка", r["nausea"]["classic_formula"])

    def test_no_promise_of_service_parity(self):
        r = tm.analyze("Текст.")
        self.assertIn("Advego", r["note"])
        self.assertIn("не совпадут", r["note"])
        self.assertIn("у сервисов своя формула", r["water"]["formula"])

    def test_match_rules_documented(self):
        r = tm.analyze("Купить диван можно тут.", keys=["купить диван"])
        rules = r["keys"][0]["match_rules"]
        self.assertIn("словоформы", rules["exact_forms"])
        self.assertIn("основы", rules["morphological"])


class TestRegistryContract(unittest.TestCase):
    """PARAM_MAP — контракт с audit.py: каждый путь должен существовать в отчёте."""

    def setUp(self):
        self.r = tm.analyze(fixture("text_ru.html"), keys=["угловой диван"], is_html=True)

    def resolve(self, path):
        node = self.r
        for part in path.split("."):
            if part.endswith("[]"):
                node = node[part[:-2]]
                self.assertTrue(node, f"пустой список: {path}")
                node = node[0]
            else:
                self.assertIn(part, node, f"нет пути {path} (сломался на {part})")
                node = node[part]
        return node

    def test_every_mapped_path_exists(self):
        for pid, path in tm.PARAM_MAP.items():
            if "*" in path or "|" in path or path.startswith("--"):
                continue
            with self.subTest(param=pid):
                self.assertIsNotNone(self.resolve(path))

    def test_registry_version_reported(self):
        self.assertEqual(self.r["registry"], tm.REGISTRY)
        self.assertIn("registry:0.2.0", tm.REGISTRY)

    def test_zone_params_cover_all_zones(self):
        mapped = {v.split(".")[-1] for k, v in tm.PARAM_MAP.items()
                  if k.startswith("content.key_in_")}
        self.assertEqual(mapped, {"title", "description", "h1", "h2_h6",
                                  "first_paragraph", "alt", "anchors", "url"})


class TestConcentrationAndGaps(unittest.TestCase):
    def test_long_sentences_threshold_is_printed(self):
        r = tm.analyze("Коротко. " + " ".join(["слово"] * 40) + ".")
        ls = r["rhythm"]["long_sentences"]
        self.assertEqual(ls["threshold_words"], tm.LONG_SENTENCE_WORDS)
        self.assertEqual(ls["count"], 1)
        self.assertEqual(ls["longest"], 40)
        self.assertIn("ориентир редактора", ls["rule"])

    def test_long_sentences_null_without_prose(self):
        self.assertIsNone(tm.analyze("# Заголовок")["rhythm"]["long_sentences"]["pct"])

    def test_missing_everywhere(self):
        r = tm.analyze("<body><h1>Кофе</h1><p>Страница про обжарку зерна тут.</p></body>",
                       keys=["угловой диван"], is_html=True)
        self.assertTrue(r["keys"][0]["missing_everywhere"])
        r2 = tm.analyze("<body><h1>Угловые диваны</h1><p>Текст про мебель тут есть.</p></body>",
                        keys=["угловой диван"], is_html=True)
        self.assertFalse(r2["keys"][0]["missing_everywhere"])

    def test_concentration_picture_not_threshold(self):
        r = tm.analyze("Угловой диван, угловой диван, угловой диван в наличии.",
                       keys=["угловой диван"])
        c = r["keys"][0]["concentration"]
        self.assertEqual(c["max_in_one_sentence"], 3)
        self.assertGreaterEqual(c["adjacent_repeats"], 1)
        self.assertIn("картина, а не процент", c["note"])
        self.assertIn("facts-2026", c["note"])

    def test_zones_with_key_counted(self):
        r = tm.analyze(fixture("text_ru.html"), keys=["угловой диван"], is_html=True)
        c = r["keys"][0]["concentration"]
        self.assertEqual(c["zones_with_data"], 8)
        self.assertGreaterEqual(c["zones_with_key"], 6)

    def test_items_with_key_numbered(self):
        r = tm.analyze(fixture("text_ru.html"), keys=["угловой диван"], is_html=True)
        h = r["keys"][0]["zones"]["h2_h6"]
        self.assertEqual(h["items_total"], 5)
        self.assertEqual([i["n"] for i in h["items_with_key"]], [1])
        self.assertIn("Как выбрать угловой диван", h["items_with_key"][0]["text"])

    def test_cooccurrence_window_documented(self):
        r = tm.analyze("Угловой диван стоит в зале. " + " ".join(["слово"] * 30) + ".",
                       keys=["угловой диван"])
        co = r["keys"][0]["cooccurrence"]
        self.assertEqual(co["window_words"], 10)
        self.assertIn("±10", co["window_rule"])


class TestPageTextChecks(unittest.TestCase):
    """Текстовая часть meta.* / ai.* / intl.*: сравнение зон между собой."""

    def page(self, head, body):
        return tm.analyze(f"<html lang='ru'><head>{head}</head><body><main>{body}"
                          f"</main></body></html>", is_html=True)["page_text"]

    def test_title_stuffing_repeats_and_caps(self):
        p = self.page("<title>ДИВАН ДИВАН ДИВАНЫ ДИВАНОВ КУПИТЬ</title>",
                      "<p>Текст страницы про мебель тут.</p>")
        self.assertEqual(p["title_stuffing"]["repeated_stems"][0]["stem"], "диван")
        self.assertEqual(p["title_stuffing"]["uppercase_pct"], 100.0)
        self.assertIn("нормы в документации нет", p["title_stuffing"]["rule"])

    def test_title_vs_h1_overlap(self):
        p = self.page("<title>Угловые диваны — Мебель</title>",
                      "<h1>Угловой диван</h1><p>Текст страницы про мебель тут.</p>")
        self.assertEqual(p["title_vs_h1"]["shared_stems"], ["диван", "углов"])
        self.assertEqual(p["title_vs_h1"]["h1_stems_in_title_pct"], 100.0)

    def test_title_vs_h1_null_without_h1(self):
        p = self.page("<title>Заголовок</title>", "<p>Текст страницы тут есть.</p>")
        self.assertIsNone(p["title_vs_h1"]["h1_stems_in_title_pct"])

    def test_desc_equals_title(self):
        p = self.page("<title>Купить диван</title>"
                      "<meta name='description' content='Купить диван'>",
                      "<p>Текст страницы про мебель тут.</p>")
        self.assertTrue(p["desc_vs_title"]["equal"])

    def test_desc_is_prefix_of_first_paragraph(self):
        p = self.page("<title>Диваны</title>"
                      "<meta name='description' content='Угловой диван закрывает две стены'>",
                      "<p>Угловой диван закрывает две стены сразу и экономит место.</p>")
        self.assertTrue(p["desc_vs_first_paragraph"]["is_prefix"])
        self.assertFalse(p["desc_vs_first_paragraph"]["equal"])

    def test_heading_stuffing_across_level(self):
        p = self.page("<title>Диваны</title>",
                      "<h2>Диван угловой</h2><h2>Диван прямой</h2><h2>Диван модульный</h2>"
                      "<p>Текст страницы про мебель тут.</p>")
        rep = p["heading_stuffing"]["repeated"]
        self.assertEqual(rep[0]["level"], "h2")
        self.assertEqual(rep[0]["in_headings"], 3)
        self.assertEqual(rep[0]["of"], 3)

    def test_heading_stuffing_needs_two_headings(self):
        p = self.page("<title>t</title>", "<h2>Диван</h2><p>Текст страницы тут есть.</p>")
        self.assertEqual(p["heading_stuffing"]["repeated"], [])

    def test_heading_length_distribution_without_threshold(self):
        p = self.page("<title>t</title>",
                      "<h2>Короткий</h2><h2>Заголовок из нескольких слов тут</h2>"
                      "<p>Текст страницы про мебель тут.</p>")
        self.assertEqual(p["heading_length"]["longest_words"], 5)
        self.assertIn("порога нет", p["heading_length"]["rule"])

    def test_language_mismatch_between_title_and_text(self):
        p = self.page("<title>Corner sofas for sale</title>",
                      "<p>Угловой диван закрывает две стены сразу.</p>")
        self.assertTrue(p["language"]["body_vs_title_mismatch"])
        self.assertEqual(p["language"]["html_lang"], "ru")
        self.assertEqual(p["language"]["title"]["latin_pct"], 100.0)
        self.assertIn("только по алфавиту", p["language"]["rule"])

    def test_numbers_with_and_without_source(self):
        r = tm.analyze("Доля выросла до 23 процентов. По данным Росстата, выросла на 5 "
                       "пунктов. В 2026 году будет больше.")
        n = r["page_text"]["numbers_sourced"]
        self.assertEqual(n["sentences_with_numbers"], 3)
        self.assertEqual(n["with_source_marker"], 2)
        self.assertEqual(n["without_source_marker"], 1)
        self.assertIn("page_facts.py", n["rule"])

    def test_answer_first_is_numbers_not_verdict(self):
        p = self.page("<title>t</title>",
                      "<p>Что такое холодный кофе? Это кофе, настоянный на холоде.</p>")
        a = p["answer_first"]
        self.assertEqual(a["first_paragraph_sentences"], 2)
        self.assertTrue(a["first_sentence_is_question"])
        self.assertEqual(a["status"], "оценка")
        self.assertIn("нормы длины пассажа", a["rule"])

    def test_markdown_page_text_has_no_title_claims(self):
        p = tm.analyze(fixture("text_ru_before.md"))["page_text"]
        self.assertIsNone(p["title_stuffing"]["uppercase_pct"])
        self.assertIsNone(p["title_vs_h1"]["title_stems_in_h1_pct"])
        self.assertFalse(p["desc_vs_title"]["equal"])
        self.assertIsNone(p["language"]["html_lang"])


class TestCompare(unittest.TestCase):
    def test_compare_cli(self):
        before = os.path.join(FIXTURES, "text_ru_before.md")
        after = os.path.join(FIXTURES, "text_ru_after.md")
        rc, data = run_cli(["--compare", before, after, "--keys", "угловой диван"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["mode"], "compare")
        self.assertEqual(data["input"], {"before": "text_ru_before.md",
                                         "after": "text_ru_after.md"})
        titles = {m["title"] for m in data["metrics"]}
        self.assertIn("слова", titles)
        self.assertEqual(data["keys"][0]["key"], "угловой диван")

    def test_compare_short_summary_to_out(self):
        before = os.path.join(FIXTURES, "text_ru_before.md")
        after = os.path.join(FIXTURES, "text_ru_after.md")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "cmp.json")
            rc, short = run_cli(["--compare", before, after, "--out", out])
            self.assertEqual(rc, 0)
            self.assertEqual(short["mode"], "compare")
            self.assertIn("слова", {c["title"] for c in short["changed"]})
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["mode"], "compare")

    def test_compare_full_report(self):
        a = tm.analyze("Угловой диван. Угловой диван. Угловой диван.", keys=["угловой диван"])
        b = tm.analyze("Угловой диван закрывает две стены.", keys=["угловой диван"])
        c = tm.compare(a, b)
        metrics = {m["id"]: m for m in c["metrics"]}
        self.assertEqual(metrics["nausea_academic_pct"]["before"] >
                         metrics["nausea_academic_pct"]["after"], True)
        self.assertEqual(c["keys"][0]["morphological"]["delta"], -2)
        self.assertIn("не говорит", c["compare_note"])

    def test_compare_zones_flag_changes(self):
        a = tm.analyze("<h1>Диваны</h1><p>Текст страницы про мебель тут.</p>",
                       keys=["угловой диван"], is_html=True)
        b = tm.analyze("<h1>Угловые диваны</h1><p>Текст страницы про мебель тут.</p>",
                       keys=["угловой диван"], is_html=True)
        c = tm.compare(a, b)
        zones = {z["zone"]: z for z in c["keys"][0]["zones"]}
        self.assertTrue(zones["h1"]["changed"])
        self.assertFalse(zones["anchors"]["changed"])

    def test_compare_missing_file(self):
        rc, data = run_cli(["--compare", os.path.join(FIXTURES, "nope.md"),
                            os.path.join(FIXTURES, "text_ru_after.md")])
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])

    def test_no_path_and_no_compare(self):
        rc, data = run_cli([])
        self.assertEqual(rc, 2)
        self.assertIn("error", data)


class TestFixturesEndToEnd(unittest.TestCase):
    def test_ru_page(self):
        rc, data = run_cli([os.path.join(FIXTURES, "text_ru.html"),
                            "--keys", "угловой диван", "--url",
                            "https://mebel-primer.example/katalog/uglovye-divany"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["lang"], "ru")
        self.assertEqual(data["readability"]["scores"][0]["status"], "оценка")
        zones = data["keys"][0]["zones"]
        self.assertTrue(zones["title"]["present"])
        self.assertTrue(zones["alt"]["present"])
        self.assertTrue(all(z["words"] for z in zones.values()))

    def test_en_page(self):
        rc, data = run_cli([os.path.join(FIXTURES, "text_en.html"),
                            "--keys", "cold brew coffee"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["lang"], "en")
        self.assertEqual(data["readability"]["scores"][0]["name"], "Flesch Reading Ease")
        self.assertTrue(data["keys"][0]["zones"]["url"]["present"])
        self.assertIsNotNone(data["passive"]["pct"])

    def test_short_summary_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "r.json")
            rc, short = run_cli([os.path.join(FIXTURES, "text_ru.html"),
                                 "--keys", "угловой диван", "--out", out])
        self.assertEqual(rc, 0)
        self.assertEqual(short["readability"]["status"], "оценка")
        key = short["keys"][0]
        self.assertIn("title", key["zones_with_key"])
        self.assertIn("alt", key["zones_with_key"])
        self.assertEqual(key["zones_empty"], [])
        self.assertIsNotNone(short["self_repeat_pct"])

    def test_markdown_reports_empty_zones(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "r.json")
            rc, short = run_cli([os.path.join(FIXTURES, "text_ru_before.md"),
                                 "--keys", "угловой диван", "--out", out])
        self.assertEqual(rc, 0)
        self.assertEqual(set(short["keys"][0]["zones_empty"]),
                         {"title", "description", "h2_h6", "url"})


class TestSafety(unittest.TestCase):
    def test_no_dangerous_calls(self):
        with open(os.path.join(SCRIPTS, "text_metrics.py"), encoding="utf-8") as fh:
            src = fh.read()
        bad = [
            r"^\s*(?:import|from)\s+(?:subprocess|socket|urllib|requests|http\.client|ctypes|pickle)\b",
            r"(?<![\w.])(?:eval|exec|compile|__import__)\(",
            r"os\.(?:system|popen|exec\w*|spawn\w*|environ|getenv)",
            r"expanduser|Path\.home",
        ]
        for rx in bad:
            self.assertIsNone(re.search(rx, src, re.M), rx)


if __name__ == "__main__":
    unittest.main()
