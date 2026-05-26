export type IssueSeverity = "error" | "warning" | "info";

export type IssueSource =
	| "live"
	| "consistency"
	| "timeline"
	| "canon"
	| "semantic"
	| "drift"
	| "unknown";

export interface NarrativeIssue {
	id: string;
	severity: IssueSeverity;
	message: string;
	code: string;
	source: IssueSource;
	entities?: string[];
	suggestion?: string;
	scene?: string | null;
}

export interface NarrativeEventDTO {
	event_type: string;
	subject: string;
	predicate: string;
	target?: string | null;
	location?: string | null;
}

export interface MemoryHit {
	id: string;
	content: string;
	score: number;
	metadata: Record<string, unknown>;
}

export interface MemoryContext {
	scenes: MemoryHit[];
	lore: MemoryHit[];
	characters: MemoryHit[];
	events: MemoryHit[];
}

export interface RelationshipEdgeDTO {
	source: string;
	target: string;
	relationship_type: string;
	strength: number;
	dimensions: Record<string, number>;
}

export interface NarrativeMutationResponse {
	success: boolean;
	error?: string;
	scene_title?: string;
	events?: NarrativeEventDTO[];
	timeline?: {
		valid: boolean;
		flashback_count: number;
		flash_forward_count: number;
		conflicts: string[];
		entries_count: number;
	};
	consistency?: {
		consistent: boolean;
		warnings: string[];
		errors: string[];
	};
	writer_warnings?: Array<{
		rule_id: string;
		severity: string;
		message: string;
		suggestion: string;
		entities: string[];
	}>;
	canon_protection?: {
		conflicts: Array<{
			rule_id: string;
			severity: string;
			message: string;
			entities: string[];
		}>;
	};
	drift?: {
		issues: Array<{
			rule_id: string;
			severity: string;
			message: string;
			character: string;
			evidence: string[];
		}>;
	};
	semantic_validation?: {
		score: number;
		notes: string[];
		provider_used?: string | null;
		issues: Array<{
			rule_id: string;
			severity: string;
			message: string;
			entities: string[];
			source: string;
			category: string;
			evidence: string[];
		}>;
	};
	multi_agent_analysis?: {
		summary: string[];
		blocking_issues: string[];
		agents: Record<string, { role: string; findings: string[] }>;
	};
	memory?: {
		retrieved: MemoryContext;
		character_state: Record<
			string,
			{
				personality: string[];
				beliefs: string[];
				knowledge: string[];
				desires: string[];
			}
		>;
	};
}

export interface ConsistencyCheckResponse {
	issue_count: number;
	issues: Array<{
		severity: string;
		code: string;
		message: string;
	}>;
}

export function stripHtml(html: string): string {
	return html
		.replace(/<style[\s\S]*?>[\s\S]*?<\/style>/gi, "")
		.replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, "")
		.replace(/<[^>]+>/g, " ")
		.replace(/&nbsp;/g, " ")
		.replace(/\s+/g, " ")
		.trim();
}

export function toSeverity(raw: string): IssueSeverity {
	const lower = (raw || "").toLowerCase();
	if (lower === "error") {
		return "error";
	}
	if (lower === "warning") {
		return "warning";
	}
	return "info";
}

export function buildIssuesFromMutation(payload: NarrativeMutationResponse): NarrativeIssue[] {
	const issues: NarrativeIssue[] = [];
	const now = Date.now();

	for (const warning of payload.writer_warnings || []) {
		issues.push({
			id: `writer-${warning.rule_id}-${now}-${issues.length}`,
			severity: toSeverity(warning.severity),
			code: warning.rule_id,
			message: warning.message,
			suggestion: warning.suggestion,
			entities: warning.entities,
			source: inferSource(warning.rule_id),
			scene: payload.scene_title,
		});
	}

	for (const conflict of payload.timeline?.conflicts || []) {
		issues.push({
			id: `timeline-${now}-${issues.length}`,
			severity: "error",
			code: "timeline_conflict",
			message: conflict,
			source: "timeline",
			scene: payload.scene_title,
		});
	}

	for (const conflict of payload.canon_protection?.conflicts || []) {
		issues.push({
			id: `canon-${conflict.rule_id}-${now}-${issues.length}`,
			severity: toSeverity(conflict.severity),
			code: conflict.rule_id,
			message: conflict.message,
			entities: conflict.entities,
			source: "canon",
			scene: payload.scene_title,
		});
	}

	for (const issue of payload.semantic_validation?.issues || []) {
		issues.push({
			id: `semantic-${issue.rule_id}-${now}-${issues.length}`,
			severity: toSeverity(issue.severity),
			code: issue.rule_id,
			message: issue.message,
			entities: issue.entities,
			source: "semantic",
			scene: payload.scene_title,
		});
	}

	for (const issue of payload.drift?.issues || []) {
		issues.push({
			id: `drift-${issue.rule_id}-${now}-${issues.length}`,
			severity: toSeverity(issue.severity),
			code: issue.rule_id,
			message: issue.message,
			entities: [issue.character],
			source: "drift",
			scene: payload.scene_title,
		});
	}

	return dedupeIssues(issues);
}

export function buildIssuesFromLiveCheck(payload: ConsistencyCheckResponse): NarrativeIssue[] {
	return (payload.issues || []).map((issue, index) => ({
		id: `live-${issue.code}-${index}`,
		severity: toSeverity(issue.severity),
		code: issue.code,
		message: issue.message,
		source: "live",
	}));
}

export function issueSortWeight(severity: IssueSeverity): number {
	if (severity === "error") {
		return 0;
	}
	if (severity === "warning") {
		return 1;
	}
	return 2;
}

export function inferSource(code: string): IssueSource {
	const c = (code || "").toLowerCase();
	if (c.includes("canon")) {
		return "canon";
	}
	if (c.includes("timeline")) {
		return "timeline";
	}
	if (c.includes("semantic") || c.includes("dialogue") || c.includes("progression")) {
		return "semantic";
	}
	if (c.includes("drift") || c.includes("personality") || c.includes("emotional")) {
		return "drift";
	}
	if (c.includes("consisten")) {
		return "consistency";
	}
	return "unknown";
}

export function dedupeIssues(issues: NarrativeIssue[]): NarrativeIssue[] {
	const seen = new Set<string>();
	const out: NarrativeIssue[] = [];
	for (const issue of issues) {
		const key = `${issue.source}|${issue.code}|${issue.message}`.toLowerCase();
		if (seen.has(key)) {
			continue;
		}
		seen.add(key);
		out.push(issue);
	}
	return out;
}
