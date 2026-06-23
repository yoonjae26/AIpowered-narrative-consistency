import { CSSProperties, useEffect, useMemo, useState } from "react";

type CharacterPBKD = {
	personality: string[];
	beliefs: string[];
	knowledge: string[];
	desires: string[];
};

type CharacterItem = {
	id: string;
	name: string;
	pbkd: CharacterPBKD;
	status: string;
	role: string;
};

type SearchResult = {
	character_id: string;
	name: string;
	matches: Record<string, string[]>;
};

const API_BASE =
	(import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8001";

function splitLines(raw: string): string[] {
	return raw
		.split(/\n|,/)
		.map((item) => item.trim())
		.filter(Boolean);
}

function joinLines(values: string[]): string {
	return values.join("\n");
}

export function PBKDLab() {
	const [characters, setCharacters] = useState<CharacterItem[]>([]);
	const [loading, setLoading] = useState(false);
	const [selectedId, setSelectedId] = useState("");
	const [personality, setPersonality] = useState("");
	const [beliefs, setBeliefs] = useState("");
	const [knowledge, setKnowledge] = useState("");
	const [desires, setDesires] = useState("");
	const [statusMessage, setStatusMessage] = useState("");
	const [searchQuery, setSearchQuery] = useState("");
	const [scopeP, setScopeP] = useState(true);
	const [scopeB, setScopeB] = useState(true);
	const [scopeK, setScopeK] = useState(true);
	const [scopeD, setScopeD] = useState(true);
	const [searchResults, setSearchResults] = useState<SearchResult[]>([]);

	const selected = useMemo(
		() => characters.find((item) => item.id === selectedId) || null,
		[characters, selectedId],
	);

	async function loadCharacters(): Promise<void> {
		setLoading(true);
		try {
			const response = await fetch(`${API_BASE}/narrative/characters`);
			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}
			const payload = (await response.json()) as CharacterItem[];
			setCharacters(payload);
			if (!selectedId && payload.length > 0) {
				setSelectedId(payload[0].id);
			}
		} catch (error) {
			setStatusMessage(error instanceof Error ? error.message : String(error));
		} finally {
			setLoading(false);
		}
	}

	async function savePBKD(): Promise<void> {
		if (!selectedId) {
			setStatusMessage("Select character first.");
			return;
		}
		setStatusMessage("Saving PBKD...");
		try {
			const response = await fetch(`${API_BASE}/narrative/characters/${selectedId}`, {
				method: "PATCH",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					pbkd: {
						personality: splitLines(personality),
						beliefs: splitLines(beliefs),
						knowledge: splitLines(knowledge),
						desires: splitLines(desires),
					},
				}),
			});
			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}
			setStatusMessage("PBKD updated.");
			await loadCharacters();
		} catch (error) {
			setStatusMessage(error instanceof Error ? error.message : String(error));
		}
	}

	async function runSearch(): Promise<void> {
		const scopes = [scopeP ? "P" : "", scopeB ? "B" : "", scopeK ? "K" : "", scopeD ? "D" : ""]
			.filter(Boolean)
			.join(",");
		if (!searchQuery.trim() || !scopes) {
			setSearchResults([]);
			return;
		}
		try {
			const response = await fetch(
				`${API_BASE}/narrative/characters/pbkd/search?query=${encodeURIComponent(searchQuery)}&scopes=${encodeURIComponent(scopes)}`,
			);
			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}
			const payload = (await response.json()) as { results: SearchResult[] };
			setSearchResults(payload.results || []);
		} catch (error) {
			setStatusMessage(error instanceof Error ? error.message : String(error));
		}
	}

	useEffect(() => {
		void loadCharacters();
	}, []);

	useEffect(() => {
		if (!selected) {
			setPersonality("");
			setBeliefs("");
			setKnowledge("");
			setDesires("");
			return;
		}
		setPersonality(joinLines(selected.pbkd?.personality || []));
		setBeliefs(joinLines(selected.pbkd?.beliefs || []));
		setKnowledge(joinLines(selected.pbkd?.knowledge || []));
		setDesires(joinLines(selected.pbkd?.desires || []));
	}, [selected?.id]);

	return (
		<section
			style={{
				background: "linear-gradient(180deg, #1b2437 0%, #11182a 100%)",
				border: "1px solid #354a70",
				borderRadius: 14,
				padding: 12,
				display: "grid",
				gap: 10,
			}}
		>
			<div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
				<h3 style={{ margin: 0, fontSize: 14, color: "#e8f0ff" }}>PBKD Lab</h3>
				<button
					type="button"
					onClick={() => void loadCharacters()}
					style={{
						border: "1px solid #395582",
						background: "#182844",
						color: "#d9e8ff",
						borderRadius: 8,
						padding: "5px 10px",
						fontSize: 12,
						cursor: "pointer",
					}}
				>
					Refresh
				</button>
			</div>

			<select
				value={selectedId}
				onChange={(event) => setSelectedId(event.target.value)}
				style={{
					background: "#0f1522",
					border: "1px solid #314568",
					color: "#dfebff",
					borderRadius: 9,
					padding: "8px 10px",
					fontSize: 12,
				}}
			>
				<option value="">Select character...</option>
				{characters.map((item) => (
					<option key={item.id} value={item.id}>
						{item.name} ({item.role}/{item.status})
					</option>
				))}
			</select>

			{loading && <div style={{ fontSize: 12, color: "#96abcf" }}>Loading characters...</div>}

			<div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
				<label style={{ display: "grid", gap: 4 }}>
					<span style={{ fontSize: 11, color: "#9db5dd" }}>P: Personality (line/comma separated)</span>
					<textarea value={personality} onChange={(event) => setPersonality(event.target.value)} rows={4} style={textareaStyle} />
				</label>
				<label style={{ display: "grid", gap: 4 }}>
					<span style={{ fontSize: 11, color: "#9db5dd" }}>B: Beliefs</span>
					<textarea value={beliefs} onChange={(event) => setBeliefs(event.target.value)} rows={4} style={textareaStyle} />
				</label>
				<label style={{ display: "grid", gap: 4 }}>
					<span style={{ fontSize: 11, color: "#9db5dd" }}>K: Knowledge</span>
					<textarea value={knowledge} onChange={(event) => setKnowledge(event.target.value)} rows={4} style={textareaStyle} />
				</label>
				<label style={{ display: "grid", gap: 4 }}>
					<span style={{ fontSize: 11, color: "#9db5dd" }}>D: Desire</span>
					<textarea value={desires} onChange={(event) => setDesires(event.target.value)} rows={4} style={textareaStyle} />
				</label>
			</div>

			<div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
				<button
					type="button"
					onClick={() => void savePBKD()}
					style={{
						border: "1px solid #3e72ff",
						background: "#2f5dd3",
						color: "white",
						borderRadius: 8,
						padding: "6px 11px",
						fontSize: 12,
						cursor: "pointer",
					}}
				>
					Save PBKD
				</button>
				<div style={{ fontSize: 12, color: "#9db5dd" }}>{statusMessage}</div>
			</div>

			<div style={{ borderTop: "1px solid #2f4160", paddingTop: 10, display: "grid", gap: 8 }}>
				<div style={{ fontSize: 12, color: "#a6bbe2", fontWeight: 700 }}>PBKD Search</div>
				<div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
					<input
						value={searchQuery}
						onChange={(event) => setSearchQuery(event.target.value)}
						placeholder="Search keyword (e.g. pacifist, revenge, distrusts)"
						style={{
							flex: "1 1 240px",
							background: "#0f1522",
							border: "1px solid #314568",
							color: "#dfebff",
							borderRadius: 9,
							padding: "8px 10px",
							fontSize: 12,
						}}
					/>
					<button
						type="button"
						onClick={() => void runSearch()}
						style={{
							border: "1px solid #3d557f",
							background: "#1b2a45",
							color: "#e6efff",
							borderRadius: 8,
							padding: "6px 11px",
							fontSize: 12,
							cursor: "pointer",
						}}
					>
						Search
					</button>
				</div>
				<div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
					<ScopeToggle label="P" checked={scopeP} onChange={setScopeP} />
					<ScopeToggle label="B" checked={scopeB} onChange={setScopeB} />
					<ScopeToggle label="K" checked={scopeK} onChange={setScopeK} />
					<ScopeToggle label="D" checked={scopeD} onChange={setScopeD} />
				</div>
				<div style={{ display: "grid", gap: 6 }}>
					{searchResults.length === 0 && <div style={{ fontSize: 12, color: "#8ea4cb" }}>No search results.</div>}
					{searchResults.map((item) => (
						<div
							key={item.character_id}
							style={{
								border: "1px solid #2f4468",
								borderRadius: 8,
								padding: "8px 10px",
								background: "#121d31",
								display: "grid",
								gap: 4,
							}}
						>
							<div style={{ fontSize: 12, fontWeight: 700, color: "#dce8ff" }}>{item.name}</div>
							{Object.entries(item.matches).map(([scope, values]) => (
								<div key={`${item.character_id}-${scope}`} style={{ fontSize: 11, color: "#a9bfe6" }}>
									{scope}: {values.join(", ")}
								</div>
							))}
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

function ScopeToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (next: boolean) => void }) {
	return (
		<label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "#b9cbed" }}>
			<input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
			{label}
		</label>
	);
}

const textareaStyle: CSSProperties = {
	background: "#0f1522",
	border: "1px solid #314568",
	color: "#dfebff",
	borderRadius: 9,
	padding: "8px 10px",
	fontSize: 12,
	resize: "vertical",
};

export default PBKDLab;
