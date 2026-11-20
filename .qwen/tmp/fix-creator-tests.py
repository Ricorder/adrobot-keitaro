"""Приводит фейк трекера и тесты создавателя к discovered-поведению стенда."""

from pathlib import Path

p = Path("/Users/rico/test/adrobot-keitaro/backend/tests/test_creator.py")
t = p.read_text()

# 1. группа FORTESTS существует на стенде по умолчанию — как источники и домены
old = 'self.groups: list[dict] = [{"id": 1, "name": "VZ adrobot test", "type": "campaigns"}]'
new = (
    'self.groups: list[dict] = [\n'
    '            {"id": 1, "name": "VZ adrobot test", "type": "campaigns"},\n'
    '            {"id": 10332, "name": "FORTESTS", "type": "campaigns"},\n'
    '        ]'
)
assert old in t
t = t.replace(old, new, 1)

# 2. POST /traffic_sources на стенде закрыт правами (проверено запросом) — фейк отражает это
old = """        if path.endswith("/traffic_sources") and request.method == "POST":
            created = {"id": self._new_id(), "name": body["name"], "state": "active"}
            self.sources.append(created)
            return httpx.Response(200, json=created)"""
new = """        if path.endswith("/traffic_sources") and request.method == "POST":
            return httpx.Response(
                403, json={"error": "You have no permission to access this page - TrafficSources"}
            )"""
assert old in t
t = t.replace(old, new, 1)

# 3. тест про создание группы/источника переписывается на переиспользование
old = """def test_group_and_source_are_created_once(session: Session) -> None:
    tracker = FakeKeitaro()
    create(session, tracker)
    assert [g["name"] for g in tracker.groups if g["name"].startswith("kolesnikov-")] == [
        "kolesnikov-group"
    ]
    assert [s["name"] for s in tracker.sources if s["name"].startswith("kolesnikov-")] == [
        "kolesnikov-source"
    ]

    create(session, tracker)
    assert len([g for g in tracker.groups if g["name"] == "kolesnikov-group"]) == 1
    assert len([s for s in tracker.sources if s["name"] == "kolesnikov-source"]) == 1"""
new = '''def test_group_and_source_are_reused_not_recreated(session: Session) -> None:
    """На стенде FORTESTS уже есть: создаватель обязан взять его, а не плодить копии."""
    tracker = FakeKeitaro()
    before_groups = len(tracker.groups)
    before_sources = len(tracker.sources)

    first = create(session, tracker)
    second = create(session, tracker, name="Вторая PR")

    assert first.group_id == 10332 and first.traffic_source_id == 2
    assert second.group_id == 10332
    assert len(tracker.groups) == before_groups
    assert len(tracker.sources) == before_sources


def test_group_is_created_when_configured_one_is_absent(session: Session) -> None:
    tracker = FakeKeitaro()
    tracker.groups = [g for g in tracker.groups if g["name"] != "FORTESTS"]
    result = create(session, tracker)
    assert result.group_id > 0
    assert any(g["name"] == "FORTESTS" for g in tracker.groups)


def test_absent_source_is_reported_with_options(session: Session) -> None:
    """Создать источник нельзя (403), поэтому ошибка должна называть доступные варианты."""
    tracker = FakeKeitaro()
    tracker.sources = [
        {"id": 2, "name": "FORTESTS"},
        {"id": 3, "name": "Другой"},
    ]
    client, settings = make_setup(tracker, session)
    settings = settings.model_copy(update={"keitaro_source_name": "Нет такой"})

    with pytest.raises(creator.CreatorError, match="закрыто правами"):
        creator.create_campaign(session, client, settings, name="PR", geo="PE", offer_id=18813)'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t)
print("test_creator.py обновлён")
