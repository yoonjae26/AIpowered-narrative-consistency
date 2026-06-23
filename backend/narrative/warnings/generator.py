"""
Warning System -- writer-facing feedback generator.

Converts ConsistencyReport errors/warnings into structured NarrativeWarning
objects with rule ID, severity, human-readable message, and actionable suggestion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WarningSeverity(str, Enum):
    INFO    = "info"
    WARNING = "warning"
    ERROR   = "error"


@dataclass
class NarrativeWarning:
    rule_id: str                       # e.g. "dead_character_reappears"
    severity: WarningSeverity
    message: str                       # writer-facing description
    suggestion: str                    # what to do about it
    entities_involved: list[str] = field(default_factory=list)
    scene: str | None = None

    def format(self) -> str:
        tag = f"[{self.severity.value.upper()}]"
        entity_str = ", ".join(self.entities_involved)
        lines = [f"{tag} {self.message}"]
        if entity_str:
            lines.append(f"  Entities: {entity_str}")
        if self.scene:
            lines.append(f"  Scene: {self.scene}")
        lines.append(f"  Suggestion: {self.suggestion}")
        return "\n".join(lines)


# Rule definitions: maps rule_id -> (severity, message_template, suggestion_template)
_RULES: dict[str, tuple[WarningSeverity, str, str]] = {
    "dead_character_reappears": (
        WarningSeverity.ERROR,
        "{entity} reappears but was previously marked as dead.",
        "Add an explicit resurrection event, or correct the character's status before this scene.",
    ),
    "canon_violation_resurrection": (
        WarningSeverity.ERROR,
        "Resurrection of {entity} may violate established world canon (resurrection forbidden).",
        "Check canon rules for this world. If resurrection is allowed, add a 'resurrection_allowed' flag to the event.",
    ),
    "impossible_location": (
        WarningSeverity.ERROR,
        "{entity} appears in two different locations simultaneously: {loc1} and {loc2}.",
        "Ensure only one scene features {entity} in a single timeline moment, or add a travel event.",
    ),
    "timeline_conflict": (
        WarningSeverity.ERROR,
        "Timeline conflict: {detail}",
        "Review the chronological order of events and correct the sequence.",
    ),
    "injured_character_active": (
        WarningSeverity.WARNING,
        "{entity} is performing active actions but is marked as injured.",
        "Consider whether {entity} has recovered, or add a healing event.",
    ),
    "orphan_relationship": (
        WarningSeverity.WARNING,
        "Relationship references '{entity}' which does not exist in the character database.",
        "Create the missing character, or remove the relationship reference.",
    ),
    "duplicate_character_name": (
        WarningSeverity.WARNING,
        "Multiple characters share the name '{entity}'. This may cause consistency errors.",
        "Use unique names or add disambiguation (e.g. 'John the Elder' vs 'John the Younger').",
    ),
    "behavior_conflicts_beliefs": (
        WarningSeverity.WARNING,
        "{entity}'s behavior in this scene conflicts with their established beliefs/traits.",
        "Review the character's trait sheet, or add a character development event that explains the change.",
    ),
    "personality_collapse": (
        WarningSeverity.ERROR,
        "{entity} behaves in a way that collapses their established personality.",
        "Add setup showing the character changed, or revise the action to match prior characterization.",
    ),
    "emotional_inconsistency": (
        WarningSeverity.WARNING,
        "{entity}'s emotional state appears inconsistent with the current event.",
        "Clarify why the character feels this way, or align the emotional beat with the event.",
    ),
    "irrational_action": (
        WarningSeverity.WARNING,
        "{entity} takes an action that conflicts with established beliefs or desires.",
        "Add motive, pressure, or an intermediate beat that explains the decision.",
    ),
    "canon_immutable_override": (
        WarningSeverity.ERROR,
        "The event attempts to override immutable canon for {entity}.",
        "Remove the contradiction, or explicitly mark the canon entry as mutable before changing it.",
    ),
    "lore_conflict_detected": (
        WarningSeverity.WARNING,
        "The scene conflicts with existing lore involving {entity}.",
        "Review matching lore facts and either align the scene or add a sanctioned override.",
    ),
    "semantic_emotional_mismatch": (
        WarningSeverity.WARNING,
        "The emotional tone around {entity} may clash with the scene's underlying event.",
        "Add an emotional bridge, interiority, or context that explains why the reaction makes sense.",
    ),
    "dialogue_inconsistency": (
        WarningSeverity.WARNING,
        "Dialogue for {entity} appears internally inconsistent.",
        "Revise the lines or add context so the contradiction feels intentional rather than accidental.",
    ),
    "unnatural_progression": (
        WarningSeverity.WARNING,
        "The scene progression around {entity} feels abrupt.",
        "Insert an intermediate beat, transition, or causal bridge to smooth the narrative flow.",
    ),
}


class WarningGenerator:
    """
    Converts raw string warnings/errors (from ConsistencyChecker, TimelineEngine)
    into structured NarrativeWarning objects.
    """

    def from_consistency_report(
        self,
        warnings: list[str],
        errors: list[str],
        scene: str | None = None,
    ) -> list[NarrativeWarning]:
        result: list[NarrativeWarning] = []
        for msg in warnings:
            result.append(self._classify(msg, WarningSeverity.WARNING, scene))
        for msg in errors:
            result.append(self._classify(msg, WarningSeverity.ERROR, scene))
        return result

    def from_timeline_report(
        self,
        conflicts: list[str],
        scene: str | None = None,
    ) -> list[NarrativeWarning]:
        result: list[NarrativeWarning] = []
        for conflict in conflicts:
            result.append(NarrativeWarning(
                rule_id="timeline_conflict",
                severity=WarningSeverity.ERROR,
                message=_RULES["timeline_conflict"][1].format(detail=conflict),
                suggestion=_RULES["timeline_conflict"][2],
                scene=scene,
            ))
        return result

    def make(
        self,
        rule_id: str,
        entities: list[str] | None = None,
        scene: str | None = None,
        **kwargs: str,
    ) -> NarrativeWarning:
        """Create a warning directly from a rule_id."""
        severity, msg_tpl, sug_tpl = _RULES.get(
            rule_id,
            (WarningSeverity.INFO, rule_id, "Review manually.")
        )
        fmt = {**({"entity": entities[0]} if entities else {}), **kwargs}
        return NarrativeWarning(
            rule_id=rule_id,
            severity=severity,
            message=msg_tpl.format_map(_SafeDict(fmt)),
            suggestion=sug_tpl.format_map(_SafeDict(fmt)),
            entities_involved=entities or [],
            scene=scene,
        )

    # ------------------------------------------------------------------
    # Classifier: map raw string -> structured warning
    # ------------------------------------------------------------------

    def _classify(
        self, msg: str, default_severity: WarningSeverity, scene: str | None
    ) -> NarrativeWarning:
        msg_lower = msg.lower()
        rule_id = "unknown"
        severity = default_severity

        if "dead" in msg_lower and ("reappear" in msg_lower or "appears" in msg_lower):
            rule_id = "dead_character_reappears"
            severity = WarningSeverity.ERROR
        elif "resurrection" in msg_lower and "canon" in msg_lower:
            rule_id = "canon_violation_resurrection"
            severity = WarningSeverity.ERROR
        elif "two" in msg_lower and "location" in msg_lower:
            rule_id = "impossible_location"
            severity = WarningSeverity.ERROR
        elif "timeline" in msg_lower or "conflict" in msg_lower:
            rule_id = "timeline_conflict"
            severity = WarningSeverity.ERROR
        elif "orphan" in msg_lower or "does not exist" in msg_lower:
            rule_id = "orphan_relationship"
            severity = WarningSeverity.WARNING
        elif "duplicate" in msg_lower or "same name" in msg_lower:
            rule_id = "duplicate_character_name"
            severity = WarningSeverity.WARNING
        elif "belief" in msg_lower or "trait" in msg_lower or "behavior" in msg_lower:
            rule_id = "behavior_conflicts_beliefs"
            severity = WarningSeverity.WARNING
        elif "personality" in msg_lower and "collapse" in msg_lower:
            rule_id = "personality_collapse"
            severity = WarningSeverity.ERROR
        elif "emotional" in msg_lower:
            rule_id = "emotional_inconsistency"
            severity = WarningSeverity.WARNING
        elif "irrational" in msg_lower:
            rule_id = "irrational_action"
            severity = WarningSeverity.WARNING
        elif "immutable canon" in msg_lower:
            rule_id = "canon_immutable_override"
            severity = WarningSeverity.ERROR
        elif "lore fact" in msg_lower or "lore conflict" in msg_lower:
            rule_id = "lore_conflict_detected"
            severity = WarningSeverity.WARNING
        elif "dialogue" in msg_lower and "inconsisten" in msg_lower:
            rule_id = "dialogue_inconsistency"
            severity = WarningSeverity.WARNING
        elif "progression" in msg_lower or "compressed" in msg_lower:
            rule_id = "unnatural_progression"
            severity = WarningSeverity.WARNING
        elif "emotional tone" in msg_lower or "joyful emotional language" in msg_lower:
            rule_id = "semantic_emotional_mismatch"
            severity = WarningSeverity.WARNING

        _, _, suggestion = _RULES.get(rule_id, (None, None, "Review manually."))
        return NarrativeWarning(
            rule_id=rule_id,
            severity=severity,
            message=msg,
            suggestion=suggestion or "Review manually.",
            scene=scene,
        )


class _SafeDict(dict):
    """dict that returns '{key}' for missing keys (safe .format_map)."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"
