type CharacterMemoryState = {
	personality: string[];
	beliefs: string[];
	knowledge: string[];
	desires: string[];
};

type Props = {
	characterState: Record<string, CharacterMemoryState>;
};

export function CharacterPanel({ characterState }: Props) {
	const entries = Object.entries(characterState || {});

	return (
		<section
			style={{
				background: "linear-gradient(180deg, #161d2c 0%, #111723 100%)",
				border: "1px solid #2f3750",
				borderRadius: 14,
				padding: 12,
			}}
		>
			<h3 style={{ margin: 0, fontSize: 14, color: "#ebf2ff" }}>Character Memory</h3>
			<div style={{ marginTop: 10, display: "grid", gap: 8 }}>
				{entries.length === 0 && <div style={{ fontSize: 12, color: "#899abe" }}>No character memory snapshot yet.</div>}
				{entries.map(([name, state]) => (
					<article key={name} style={{ border: "1px solid #2d3650", borderRadius: 10, padding: 10, background: "#131b29" }}>
						<h4 style={{ margin: 0, fontSize: 13, color: "#d9e7ff" }}>{name}</h4>
						<div style={{ marginTop: 6, fontSize: 12, color: "#adc0e3" }}>
							<div>Personality: {state.personality.join(", ") || "-"}</div>
							<div>Beliefs: {state.beliefs.join(", ") || "-"}</div>
							<div>Knowledge: {state.knowledge.join(", ") || "-"}</div>
							<div>Desires: {state.desires.join(", ") || "-"}</div>
						</div>
					</article>
				))}
			</div>
		</section>
	);
}

export default CharacterPanel;
