import { NarrativeEventDTO } from "../../stores";

type Props = {
	events: NarrativeEventDTO[];
	conflicts: string[];
};

function colorForEvent(eventType: string): string {
	if (eventType.includes("murder") || eventType.includes("death")) {
		return "#ff6f6f";
	}
	if (eventType.includes("travel")) {
		return "#79d8ff";
	}
	if (eventType.includes("alliance") || eventType.includes("marriage")) {
		return "#72e1ac";
	}
	if (eventType.includes("betrayal")) {
		return "#ffc86f";
	}
	return "#a4b2d3";
}

export function TimelineView({ events, conflicts }: Props) {
	const points = events.map((event, index) => {
		const x = 30 + index * 140;
		return { event, x, y: 56 };
	});
	const width = Math.max(320, 50 + events.length * 140);

	return (
		<section
			style={{
				background: "linear-gradient(180deg, #171f2f 0%, #0f1420 100%)",
				border: "1px solid #2d3751",
				borderRadius: 14,
				padding: 12,
			}}
		>
			<header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
				<h3 style={{ margin: 0, fontSize: 14, color: "#e6efff" }}>Timeline Panel</h3>
				<span style={{ fontSize: 12, color: conflicts.length ? "#ffc07f" : "#8cd9ad" }}>
					{conflicts.length ? `${conflicts.length} conflict(s)` : "Chronology stable"}
				</span>
			</header>

			<div style={{ marginTop: 10, overflowX: "auto", paddingBottom: 4 }}>
				<svg width={width} height={120}>
					<line x1={24} y1={56} x2={width - 24} y2={56} stroke="#445272" strokeWidth={2} />
					{points.map(({ event, x, y }, index) => (
						<g key={`${event.event_type}-${index}`}>
							<circle cx={x} cy={y} r={10} fill={colorForEvent(event.event_type)} stroke="#0c1019" strokeWidth={2} />
							<text x={x} y={84} fill="#d5e2ff" textAnchor="middle" style={{ fontSize: 10 }}>
								{event.event_type}
							</text>
						</g>
					))}
				</svg>
			</div>

			<div style={{ display: "grid", gap: 6 }}>
				{events.slice(0, 8).map((event, index) => (
					<div key={`${event.event_type}-${index}`} style={{ border: "1px solid #2e3850", borderRadius: 8, padding: "8px 10px", color: "#d6e3ff" }}>
						<div style={{ fontSize: 11, color: "#91a4ca" }}>{event.event_type}</div>
						<div style={{ fontSize: 13, marginTop: 2 }}>{event.predicate}</div>
					</div>
				))}
			</div>
		</section>
	);
}

export default TimelineView;
