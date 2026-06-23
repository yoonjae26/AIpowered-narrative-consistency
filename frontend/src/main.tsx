import React from "react";
import ReactDOM from "react-dom/client";

import { NarrativeEditor } from "./components/editor";

function DemoShell() {
	const apiBase =
		(import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8001";

	return (
		<>
			<div
				style={{
					position: "fixed",
					top: 12,
					right: 12,
					zIndex: 20,
					padding: "10px 12px",
					borderRadius: 12,
					background: "rgba(9, 14, 24, 0.92)",
					border: "1px solid rgba(126, 161, 225, 0.35)",
					color: "#dfeaff",
					fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif",
					fontSize: 12,
					boxShadow: "0 12px 30px rgba(0, 0, 0, 0.28)",
					maxWidth: 320,
				}}
			>
				<div style={{ fontWeight: 700, marginBottom: 4 }}>NarrativeOS Demo</div>
				<div>API base: {apiBase}</div>
				<div style={{ color: "#9cb1d8", marginTop: 4 }}>
					Run backend first, then use Run Scene to trigger mutation, consistency,
					timeline, graph and memory retrieval.
				</div>
			</div>
			<NarrativeEditor />
		</>
	);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
	<React.StrictMode>
		<DemoShell />
	</React.StrictMode>,
);