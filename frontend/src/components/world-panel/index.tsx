import { MemoryContext } from "../../stores";

type Props = {
	memory: MemoryContext | null;
};

function MemorySection({ title, items }: { title: string; items: { id: string; content: string; score: number }[] }) {
	return (
		<section style={{ borderTop: "1px solid #2d3447", paddingTop: 10, marginTop: 10 }}>
			<h4 style={{ margin: 0, fontSize: 12, letterSpacing: 0.4, textTransform: "uppercase", color: "#9db2db" }}>{title}</h4>
			<div style={{ display: "grid", gap: 8, marginTop: 8 }}>
				{items.length === 0 && <div style={{ fontSize: 12, color: "#7989aa" }}>No signals</div>}
				{items.map((item) => (
					<article key={item.id} style={{ background: "#141a27", border: "1px solid #2a3246", borderRadius: 8, padding: 8 }}>
						<div style={{ fontSize: 12, color: "#d5def5" }}>{item.content}</div>
						<div style={{ fontSize: 11, color: "#8ea0c5", marginTop: 6 }}>score {item.score.toFixed(3)}</div>
					</article>
				))}
			</div>
		</section>
	);
}

export function WorldPanel({ memory }: Props) {
	return (
		<aside
			style={{
				background: "linear-gradient(180deg, #141a27 0%, #0f131e 100%)",
				border: "1px solid #2b3347",
				borderRadius: 14,
				padding: 12,
				color: "#e8efff",
				minHeight: 260,
			}}
		>
			<h3 style={{ margin: 0, fontSize: 14, letterSpacing: 0.3 }}>Lore Sidebar</h3>
			<p style={{ margin: "6px 0 0", fontSize: 12, color: "#93a5c9" }}>Semantic memory and canon context retrieved from backend.</p>

			<MemorySection title="Lore" items={memory?.lore || []} />
			<MemorySection title="Scenes" items={memory?.scenes || []} />
			<MemorySection title="Characters" items={memory?.characters || []} />
			<MemorySection title="Events" items={memory?.events || []} />
		</aside>
	);
}

export default WorldPanel;
