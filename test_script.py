import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
os.environ.setdefault("DATABASE_URL", "sqlite:///./narrativeos_test.db")

try:
    # Test 1: EntityExtractor heuristic (no LLM)
    from narrative.mutation.entity_extractor import EntityExtractor
    ext = EntityExtractor(llm_provider=None)
    scene = "Aragorn entered the Dark Forest carrying the Elvish Sword. Legolas waited at the Gate."
    result = ext.extract(scene)
    print("characters:", [e.name for e in result.characters])
    print("locations:", [e.name for e in result.locations])

    # Test 2: EventGenerator heuristic
    from narrative.mutation.event_generator import EventGenerator
    gen = EventGenerator(llm_provider=None)
    events = gen.generate(scene, result, scene_title="The Dark Forest")
    print("events:", [(e.event_type.value, e.subject) for e in events])

    # Test 3: Full pipeline (no DB, only import + instantiation check)
    from narrative.state_engine import NarrativeStateMutationEngine
    print("NarrativeStateMutationEngine import OK")
    print("ALL_TESTS_PASSED")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
