import { RelationshipEdgeDTO } from "../../stores";

type Props = {
	edges: RelationshipEdgeDTO[];
};

type NodePoint = {
	id: string;
	x: number;
	y: number;
};

function edgeColor(edge: RelationshipEdgeDTO): string {
	if ((edge.dimensions.hatred || 0) > 0.5) {
		return "#ff7f7f";
	}
	if ((edge.dimensions.alliance || 0) > 0.5) {
		return "#81e8b5";
	}
	if ((edge.dimensions.trust || 0) > 0.5) {
		return "#77c8ff";
	}
	return "#d0c2ff";
}

export function RelationshipGraph({ edges }: Props) {
	const unique = Array.from(
		new Set(edges.flatMap((edge) => [edge.source, edge.target]).filter(Boolean)),
	);

	const centerX = 230;
	const centerY = 130;
	const radius = Math.max(64, unique.length * 16);
	const nodes: NodePoint[] = unique.map((id, index) => {
		const angle = (Math.PI * 2 * index) / Math.max(unique.length, 1);
		return {
			id,
			x: centerX + Math.cos(angle) * radius,
			y: centerY + Math.sin(angle) * radius,
		};
	});

	function getNode(id: string): NodePoint | undefined {
		return nodes.find((node) => node.id === id);
	}

	return (
		<section
			style={{
				background: "linear-gradient(180deg, #141c2a 0%, #0d121c 100%)",
				border: "1px solid #2b3448",
				borderRadius: 14,
				padding: 12,
			}}
		>
			<header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
				<h3 style={{ margin: 0, fontSize: 14, color: "#e6f0ff" }}>Relationship Graph</h3>
				<span style={{ fontSize: 12, color: "#93a7ce" }}>{edges.length} links</span>
			</header>

			{edges.length === 0 ? (
				<div style={{ fontSize: 12, color: "#8498bf", marginTop: 10 }}>No relationship edges yet. Run scene mutation to populate graph.</div>
			) : (
				<svg width="100%" viewBox="0 0 460 260" style={{ marginTop: 10 }}>
					{edges.map((edge, index) => {
						const source = getNode(edge.source);
						const target = getNode(edge.target);
						if (!source || !target) {
							return null;
						}
						return (
							<g key={`${edge.source}-${edge.target}-${index}`}>
								<line
									x1={source.x}
									y1={source.y}
									x2={target.x}
									y2={target.y}
									stroke={edgeColor(edge)}
									strokeOpacity={0.85}
									strokeWidth={1 + Math.min(edge.strength, 1) * 2.5}
								/>
							</g>
						);
					})}

					{nodes.map((node) => (
						<g key={node.id}>
							<circle cx={node.x} cy={node.y} r={12} fill="#1f2d4b" stroke="#8bb2ff" strokeWidth={1.5} />
							<text x={node.x} y={node.y + 24} textAnchor="middle" fill="#d9e8ff" style={{ fontSize: 11 }}>
								{node.id}
							</text>
						</g>
					))}
				</svg>
			)}
		</section>
	);
}

export default RelationshipGraph;
