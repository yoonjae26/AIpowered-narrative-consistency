const $ = (selector) => document.querySelector(selector);

const elements = {
  apiBase: $("#apiBase"),
  healthBtn: $("#healthBtn"),
  healthOutput: $("#healthOutput"),
  kgBtn: $("#kgBtn"),
  kgOutput: $("#kgOutput"),
  graphBtn: $("#graphBtn"),
  graphOutput: $("#graphOutput"),

  scenarioList: $("#scenarioList"),
  sceneTitle: $("#sceneTitle"),
  sceneText: $("#sceneText"),
  allowOverride: $("#allowOverride"),
  mutationBtn: $("#mutationBtn"),
  mutationOutput: $("#mutationOutput"),
  gateDecisionBadge: $("#gateDecisionBadge"),
  gateMessage: $("#gateMessage"),
  gateReasons: $("#gateReasons"),
  rewriteInstructions: $("#rewriteInstructions"),
  rewriteTone: $("#rewriteTone"),
  rewriteBtn: $("#rewriteBtn"),
  applyRewriteBtn: $("#applyRewriteBtn"),
  rewriteStatus: $("#rewriteStatus"),
  rewriteOutput: $("#rewriteOutput"),
  patchDecisionEditor: $("#patchDecisionEditor"),

  characterSelect: $("#characterSelect"),
  loadCharactersBtn: $("#loadCharactersBtn"),
  pbkdPersonality: $("#pbkdPersonality"),
  pbkdBeliefs: $("#pbkdBeliefs"),
  pbkdKnowledge: $("#pbkdKnowledge"),
  pbkdDesires: $("#pbkdDesires"),
  savePbkdBtn: $("#savePbkdBtn"),
  pbkdStatus: $("#pbkdStatus"),

  pbkdSearchQuery: $("#pbkdSearchQuery"),
  pbkdSearchBtn: $("#pbkdSearchBtn"),
  scopeP: $("#scopeP"),
  scopeB: $("#scopeB"),
  scopeK: $("#scopeK"),
  scopeD: $("#scopeD"),
  pbkdSearchOutput: $("#pbkdSearchOutput"),

  consistencyText: $("#consistencyText"),
  consistencyBtn: $("#consistencyBtn"),
  consistencyOutput: $("#consistencyOutput"),

  queryText: $("#queryText"),
  queryBtn: $("#queryBtn"),
  queryOutput: $("#queryOutput"),
};

const scenarios = [
  {
    id: "gate-approve",
    title: "Stable progression",
    description: "Low-risk scene for approve decision.",
    sceneTitle: "Quiet planning in the archive",
    sceneText:
      "John and Mira review old maps in the archive. They update their plan to rebuild the sanctuary and agree to avoid violent conflict.",
    consistencyText:
      "John says he values trust and then coordinates with Mira using transparent communication.",
    queryText: "What are John and Mira planning?",
  },
  {
    id: "gate-override",
    title: "Canon pressure",
    description: "Likely to trigger needs-override decision.",
    sceneTitle: "Return of the forbidden heir",
    sceneText:
      "Despite old canon that resurrection is forbidden, Mira performs a ritual to bring Anna back to life in the main hall.",
    consistencyText:
      "The world forbids resurrection, yet characters attempt it in public.",
    queryText: "Did anyone violate canon?",
  },
  {
    id: "gate-reject",
    title: "Hard conflict",
    description: "Likely to trigger reject from consistency + drift.",
    sceneTitle: "Broken oath and lethal contradiction",
    sceneText:
      "A known pacifist character murders an ally immediately after promising eternal protection and claiming they never use violence.",
    consistencyText:
      "The pacifist vow and the violent action happen in the same moment.",
    queryText: "Why was this scene rejected?",
  },
];

let activeScenarioId = scenarios[0].id;
let characters = [];
let lastRewrite = null;

function apiBase() {
  return elements.apiBase.value.replace(/\/$/, "");
}

function print(target, payload) {
  target.textContent =
    typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

function linesToArray(raw) {
  return raw
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function arrayToLines(values) {
  if (!Array.isArray(values)) {
    return "";
  }
  return values.join("\n");
}

function setGateDecision(decision) {
  elements.gateDecisionBadge.classList.remove(
    "decision-none",
    "decision-approve",
    "decision-reject",
    "decision-override",
  );

  if (decision === "approve") {
    elements.gateDecisionBadge.classList.add("decision-approve");
    elements.gateDecisionBadge.textContent = "APPROVE";
    return;
  }
  if (decision === "reject") {
    elements.gateDecisionBadge.classList.add("decision-reject");
    elements.gateDecisionBadge.textContent = "REJECT";
    return;
  }
  if (decision === "needs-override") {
    elements.gateDecisionBadge.classList.add("decision-override");
    elements.gateDecisionBadge.textContent = "NEEDS OVERRIDE";
    return;
  }

  elements.gateDecisionBadge.classList.add("decision-none");
  elements.gateDecisionBadge.textContent = "NO DECISION";
}

function renderGate(result) {
  const gate = result?.gate || {};
  const decision = result?.decision || gate.decision || "";
  setGateDecision(decision);

  elements.gateMessage.textContent =
    gate.message || result?.error || "No gate message from backend.";

  elements.gateReasons.innerHTML = "";
  const blocking = gate.blocking_reasons || [];
  const overrideable = gate.overrideable_reasons || [];

  for (const reason of blocking.slice(0, 6)) {
    const item = document.createElement("div");
    item.className = "reason-chip reason-blocking";
    item.textContent = reason;
    elements.gateReasons.appendChild(item);
  }

  for (const reason of overrideable.slice(0, 6)) {
    const item = document.createElement("div");
    item.className = "reason-chip reason-override";
    item.textContent = reason;
    elements.gateReasons.appendChild(item);
  }
}

function renderRewrite(result) {
  lastRewrite = result || null;
  const issues = Array.isArray(result?.issues) ? result.issues : [];
  const patches = Array.isArray(result?.selected_patches)
    ? result.selected_patches
    : Array.isArray(result?.patches)
      ? result.patches
      : [];
  const ranked = Array.isArray(result?.ranked_candidates) ? result.ranked_candidates : [];
  const applied = Array.isArray(result?.applied_patches) ? result.applied_patches : [];

  const defaultDecisions = patches.map((patch) => ({
    patch_id: patch.patch_id,
    action: patch?.verification?.accepted ? "accept" : "reject",
  }));
  elements.patchDecisionEditor.value = JSON.stringify(defaultDecisions, null, 2);

  print(elements.rewriteOutput, {
    summary: result?.summary || "",
    provider_used: result?.provider_used || null,
    review_required: Boolean(result?.review_required),
    issue_count: issues.length,
    patch_count: patches.length,
    ranked_issue_groups: ranked.length,
    applied_count: applied.filter((item) => item?.applied).length,
    knowledge_graph_evidence: result?.knowledge_graph_evidence || [],
    issues,
    ranked_candidates: ranked,
    patches,
    applied_patches: applied,
    risk_notes: result?.risk_notes || [],
  });

  if (result?.provider_used) {
    elements.rewriteStatus.textContent = `Provider: ${result.provider_used} | issues=${issues.length} | patches=${patches.length}`;
  } else {
    elements.rewriteStatus.textContent = `Fallback structured patch mode | issues=${issues.length} | patches=${patches.length}`;
  }
}

function applyScenario(id) {
  const scenario = scenarios.find((item) => item.id === id);
  if (!scenario) {
    return;
  }
  activeScenarioId = id;
  elements.sceneTitle.value = scenario.sceneTitle;
  elements.sceneText.value = scenario.sceneText;
  elements.consistencyText.value = scenario.consistencyText;
  elements.queryText.value = scenario.queryText;
  renderScenarios();
}

function renderScenarios() {
  elements.scenarioList.innerHTML = "";
  for (const scenario of scenarios) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `scenario-card${scenario.id === activeScenarioId ? " active" : ""}`;
    button.innerHTML = `<h3>${scenario.title}</h3><p>${scenario.description}</p>`;
    button.addEventListener("click", () => applyScenario(scenario.id));
    elements.scenarioList.appendChild(button);
  }
}

function fillPbkdForm(character) {
  const pbkd = character?.pbkd || {};
  elements.pbkdPersonality.value = arrayToLines(pbkd.personality || []);
  elements.pbkdBeliefs.value = arrayToLines(pbkd.beliefs || []);
  elements.pbkdKnowledge.value = arrayToLines(pbkd.knowledge || []);
  elements.pbkdDesires.value = arrayToLines(pbkd.desires || []);
}

function renderCharacterSelect() {
  elements.characterSelect.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select character...";
  elements.characterSelect.appendChild(placeholder);

  for (const character of characters) {
    const option = document.createElement("option");
    option.value = character.id;
    option.textContent = `${character.name} (${character.role}/${character.status})`;
    elements.characterSelect.appendChild(option);
  }

  if (characters.length > 0) {
    elements.characterSelect.value = characters[0].id;
    fillPbkdForm(characters[0]);
  }
}

async function callJson(path, options = {}) {
  const response = await fetch(`${apiBase()}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!response.ok) {
    throw new Error(JSON.stringify({ status: response.status, data }, null, 2));
  }
  return data;
}

async function withButton(button, output, task) {
  const prev = button.textContent;
  button.disabled = true;
  button.textContent = "Running...";
  try {
    const data = await task();
    print(output, data);
  } catch (error) {
    print(output, error instanceof Error ? error.message : String(error));
  } finally {
    button.disabled = false;
    button.textContent = prev;
  }
}

async function loadCharacters() {
  elements.pbkdStatus.textContent = "Loading characters...";
  try {
    const payload = await callJson("/narrative/characters");
    characters = Array.isArray(payload) ? payload : [];
    renderCharacterSelect();
    elements.pbkdStatus.textContent = `Loaded ${characters.length} character(s).`;
  } catch (error) {
    elements.pbkdStatus.textContent =
      error instanceof Error ? error.message : String(error);
  }
}

async function savePbkd() {
  const characterId = elements.characterSelect.value;
  if (!characterId) {
    elements.pbkdStatus.textContent = "Select a character first.";
    return;
  }

  elements.savePbkdBtn.disabled = true;
  elements.pbkdStatus.textContent = "Saving PBKD...";
  try {
    await callJson(`/narrative/characters/${characterId}`, {
      method: "PATCH",
      body: JSON.stringify({
        pbkd: {
          personality: linesToArray(elements.pbkdPersonality.value),
          beliefs: linesToArray(elements.pbkdBeliefs.value),
          knowledge: linesToArray(elements.pbkdKnowledge.value),
          desires: linesToArray(elements.pbkdDesires.value),
        },
      }),
    });
    elements.pbkdStatus.textContent = "PBKD updated successfully.";
    await loadCharacters();
  } catch (error) {
    elements.pbkdStatus.textContent =
      error instanceof Error ? error.message : String(error);
  } finally {
    elements.savePbkdBtn.disabled = false;
  }
}

async function rewriteScene() {
  const sourceText = elements.sceneText.value.trim();
  if (!sourceText) {
    elements.rewriteStatus.textContent = "Scene text is empty.";
    return;
  }

  elements.rewriteBtn.disabled = true;
  elements.rewriteStatus.textContent = "Verifying and generating structured patches...";
  try {
    const payload = await callJson("/narrative/rewrite/structured", {
      method: "POST",
      body: JSON.stringify({
        source_text: sourceText,
        scene_title: elements.sceneTitle.value.trim() || null,
        instructions: elements.rewriteInstructions.value.trim() || null,
        target_tone: elements.rewriteTone.value.trim() || null,
        max_issues: 5,
        candidates_per_issue: 3,
        auto_apply: false,
        strict_reverification: true,
        style_notes: ["keep pacing clean", "preserve canonical facts"],
      }),
    });
    renderRewrite(payload);
  } catch (error) {
    renderRewrite({
      provider_used: null,
      reason: error instanceof Error ? error.message : String(error),
      patched_text: sourceText,
      summary: "Structured auto-editor failed.",
      issues: [],
      patches: [],
      applied_patches: [],
      risk_notes: [],
    });
  } finally {
    elements.rewriteBtn.disabled = false;
  }
}

function applyRewrite() {
  const selected = Array.isArray(lastRewrite?.selected_patches) ? lastRewrite.selected_patches : [];
  if (selected.length === 0) {
    elements.rewriteStatus.textContent = "Run Verify + Patch first.";
    return;
  }

  let decisions = [];
  try {
    const parsed = JSON.parse(elements.patchDecisionEditor.value || "[]");
    decisions = Array.isArray(parsed) ? parsed : [];
  } catch {
    elements.rewriteStatus.textContent = "Invalid Patch Decisions JSON.";
    return;
  }

  elements.applyRewriteBtn.disabled = true;
  elements.rewriteStatus.textContent = "Reviewing selected patches...";
  void callJson("/narrative/rewrite/structured/review", {
    method: "POST",
    body: JSON.stringify({
      source_text: elements.sceneText.value,
      scene_title: elements.sceneTitle.value.trim() || null,
      instructions: elements.rewriteInstructions.value.trim() || null,
      target_tone: elements.rewriteTone.value.trim() || null,
      preserve_canon: true,
      preserve_characters: true,
      patches: selected,
      decisions,
      strict_reverification: true,
    }),
  })
    .then((payload) => {
      const rewritten = payload?.patched_text;
      if (typeof rewritten === "string" && rewritten.trim()) {
        elements.sceneText.value = rewritten;
        elements.consistencyText.value = rewritten;
      }
      print(elements.rewriteOutput, payload);
      elements.rewriteStatus.textContent = `Review applied. accepted=${(payload?.accepted_patches || []).length}, rejected=${(payload?.rejected_patches || []).length}`;
    })
    .catch((error) => {
      elements.rewriteStatus.textContent =
        error instanceof Error ? error.message : String(error);
    })
    .finally(() => {
      elements.applyRewriteBtn.disabled = false;
    });
}

async function searchPbkd() {
  const query = elements.pbkdSearchQuery.value.trim();
  const scopes = [
    elements.scopeP.checked ? "P" : "",
    elements.scopeB.checked ? "B" : "",
    elements.scopeK.checked ? "K" : "",
    elements.scopeD.checked ? "D" : "",
  ]
    .filter(Boolean)
    .join(",");

  if (!query || !scopes) {
    print(elements.pbkdSearchOutput, "Provide query and at least one scope.");
    return;
  }

  await withButton(elements.pbkdSearchBtn, elements.pbkdSearchOutput, () =>
    callJson(
      `/narrative/characters/pbkd/search?query=${encodeURIComponent(query)}&scopes=${encodeURIComponent(scopes)}`,
    ),
  );
}

elements.characterSelect.addEventListener("change", () => {
  const found = characters.find((item) => item.id === elements.characterSelect.value);
  fillPbkdForm(found || null);
});

elements.loadCharactersBtn.addEventListener("click", () => {
  void loadCharacters();
});

elements.savePbkdBtn.addEventListener("click", () => {
  void savePbkd();
});

elements.pbkdSearchBtn.addEventListener("click", () => {
  void searchPbkd();
});

elements.healthBtn.addEventListener("click", () =>
  withButton(elements.healthBtn, elements.healthOutput, () => callJson("/health")),
);

elements.kgBtn.addEventListener("click", () =>
  withButton(elements.kgBtn, elements.kgOutput, () =>
    callJson("/narrative/knowledge-graph/summary"),
  ),
);

elements.graphBtn.addEventListener("click", () =>
  withButton(elements.graphBtn, elements.graphOutput, () =>
    callJson("/narrative/relationships/graph?dimension=trust&minimum=0.3"),
  ),
);

elements.consistencyBtn.addEventListener("click", () =>
  withButton(elements.consistencyBtn, elements.consistencyOutput, () =>
    callJson("/consistency/check", {
      method: "POST",
      body: JSON.stringify({
        narrative: elements.consistencyText.value,
        reference_notes: [],
      }),
    }),
  ),
);

elements.queryBtn.addEventListener("click", () =>
  withButton(elements.queryBtn, elements.queryOutput, () =>
    callJson("/narrative/query", {
      method: "POST",
      body: JSON.stringify({ query: elements.queryText.value }),
    }),
  ),
);

elements.rewriteBtn.addEventListener("click", () => {
  void rewriteScene();
});

elements.applyRewriteBtn.addEventListener("click", () => {
  applyRewrite();
});

elements.mutationBtn.addEventListener("click", async () => {
  const prev = elements.mutationBtn.textContent;
  elements.mutationBtn.disabled = true;
  elements.mutationBtn.textContent = "Running...";

  try {
    const payload = await callJson("/narrative/state-mutation", {
      method: "POST",
      body: JSON.stringify({
        scene_text: elements.sceneText.value,
        scene_title: elements.sceneTitle.value,
        context: {
          branch: "main",
          memory_limit: 8,
          allow_canon_override: elements.allowOverride.checked,
        },
      }),
    });

    renderGate(payload);
    print(elements.mutationOutput, payload);
  } catch (error) {
    setGateDecision("reject");
    elements.gateMessage.textContent =
      error instanceof Error ? error.message : String(error);
    print(elements.mutationOutput, error instanceof Error ? error.message : String(error));
  } finally {
    elements.mutationBtn.disabled = false;
    elements.mutationBtn.textContent = prev;
  }
});

renderScenarios();
applyScenario(activeScenarioId);
setGateDecision("");
void loadCharacters();