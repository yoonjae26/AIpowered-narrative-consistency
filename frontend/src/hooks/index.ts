import { useEffect, useMemo, useRef, useState } from "react";
import {
	buildIssuesFromLiveCheck,
	buildIssuesFromMutation,
	dedupeIssues,
	issueSortWeight,
	NarrativeIssue,
	NarrativeMutationResponse,
	RelationshipEdgeDTO,
	stripHtml,
} from "../stores";

const API_BASE = "http://localhost:8000";

function mergeReferenceNotes(result: NarrativeMutationResponse | null): string[] {
	if (!result?.memory?.retrieved) {
		return [];
	}
	const merged = [
		...(result.memory.retrieved.lore || []),
		...(result.memory.retrieved.scenes || []),
		...(result.memory.retrieved.characters || []),
	];
	return merged.slice(0, 20).map((item) => item.content);
}

export function useDebouncedValue<T>(value: T, delayMs = 500): T {
	const [debounced, setDebounced] = useState(value);
	useEffect(() => {
		const timer = window.setTimeout(() => setDebounced(value), delayMs);
		return () => window.clearTimeout(timer);
	}, [value, delayMs]);
	return debounced;
}

export function useNarrativeIde() {
	const [sceneTitle, setSceneTitle] = useState("Untitled Scene");
	const [editorHtml, setEditorHtml] = useState("<p>Write your scene here...</p>");
	const [isRunning, setIsRunning] = useState(false);
	const [isChecking, setIsChecking] = useState(false);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);
	const [lastResult, setLastResult] = useState<NarrativeMutationResponse | null>(null);
	const [pipelineIssues, setPipelineIssues] = useState<NarrativeIssue[]>([]);
	const [liveIssues, setLiveIssues] = useState<NarrativeIssue[]>([]);
	const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
	const [relationshipEdges, setRelationshipEdges] = useState<RelationshipEdgeDTO[]>([]);
	const liveRequestSeq = useRef(0);

	const plainText = useMemo(() => stripHtml(editorHtml), [editorHtml]);
	const debouncedText = useDebouncedValue(plainText, 650);

	const issues = useMemo(() => {
		const merged = dedupeIssues([...liveIssues, ...pipelineIssues]);
		return merged.sort((a, b) => issueSortWeight(a.severity) - issueSortWeight(b.severity));
	}, [liveIssues, pipelineIssues]);

	const selectedIssue = useMemo(
		() => issues.find((issue) => issue.id === selectedIssueId) || null,
		[issues, selectedIssueId],
	);

	async function runPipeline(): Promise<void> {
		if (!plainText.trim()) {
			return;
		}
		setIsRunning(true);
		setErrorMessage(null);
		try {
			const response = await fetch(`${API_BASE}/narrative/state-mutation`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					scene_text: plainText,
					scene_title: sceneTitle,
					context: { branch: "main", memory_limit: 10 },
				}),
			});
			const payload = (await response.json()) as NarrativeMutationResponse;
			if (!response.ok || !payload.success) {
				throw new Error(payload.error || `HTTP ${response.status}`);
			}
			setLastResult(payload);
			const issuesFromMutation = buildIssuesFromMutation(payload);
			setPipelineIssues(issuesFromMutation);
			await refreshRelationshipGraph();
		} catch (error) {
			setErrorMessage(error instanceof Error ? error.message : String(error));
		} finally {
			setIsRunning(false);
		}
	}

	async function runLiveCheck(text: string): Promise<void> {
		const seq = ++liveRequestSeq.current;
		if (!text.trim()) {
			setLiveIssues([]);
			return;
		}
		setIsChecking(true);
		try {
			const response = await fetch(`${API_BASE}/consistency/check`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					narrative: text,
					reference_notes: mergeReferenceNotes(lastResult),
				}),
			});
			const payload = await response.json();
			if (seq !== liveRequestSeq.current) {
				return;
			}
			if (response.ok) {
				setLiveIssues(buildIssuesFromLiveCheck(payload));
			}
		} catch {
			if (seq === liveRequestSeq.current) {
				setLiveIssues([]);
			}
		} finally {
			if (seq === liveRequestSeq.current) {
				setIsChecking(false);
			}
		}
	}

	async function refreshRelationshipGraph(): Promise<void> {
		const dimensions = ["trust", "friendship", "hatred", "alliance"];
		const allEdges: RelationshipEdgeDTO[] = [];
		for (const dimension of dimensions) {
			try {
				const response = await fetch(
					`${API_BASE}/narrative/relationships/graph?dimension=${encodeURIComponent(dimension)}&minimum=0.3`,
				);
				if (!response.ok) {
					continue;
				}
				const payload = (await response.json()) as RelationshipEdgeDTO[];
				allEdges.push(...payload);
			} catch {
				// ignore graph refresh errors
			}
		}
		const seen = new Set<string>();
		const deduped: RelationshipEdgeDTO[] = [];
		for (const edge of allEdges) {
			const key = `${edge.source}|${edge.target}|${edge.relationship_type}`;
			if (seen.has(key)) {
				continue;
			}
			seen.add(key);
			deduped.push(edge);
		}
		setRelationshipEdges(deduped);
	}

	function applyFormatting(command: "bold" | "italic" | "underline" | "insertUnorderedList"): void {
		document.execCommand(command);
	}

	function clearIssues(): void {
		setPipelineIssues([]);
		setLiveIssues([]);
		setSelectedIssueId(null);
	}

	useEffect(() => {
		void runLiveCheck(debouncedText);
	}, [debouncedText]);

	return {
		sceneTitle,
		setSceneTitle,
		editorHtml,
		setEditorHtml,
		plainText,
		isRunning,
		isChecking,
		errorMessage,
		lastResult,
		issues,
		selectedIssue,
		selectedIssueId,
		setSelectedIssueId,
		relationshipEdges,
		runPipeline,
		applyFormatting,
		clearIssues,
	};
}
