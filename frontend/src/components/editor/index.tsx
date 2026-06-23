import { useRef } from "react";
import { useNarrativeIde } from "../../hooks";
import { CharacterPanel } from "../character-panel";
import { ConsistencySidebar } from "../consistency-sidebar";
import { GatePanel } from "../gate-panel";
import { PBKDLab } from "../pbkd-lab";
import { RelationshipGraph } from "../relationship-graph";
import { TimelineView } from "../timeline-view";
import { WorldPanel } from "../world-panel";

function ToolbarButton({ label, onClick }: { label: string; onClick: () => void }) {
	return (
		<button
			type="button"
			onClick={onClick}
			style={{
				border: "1px solid #344562",
				background: "#1a2438",
				color: "#dfe9ff",
				borderRadius: 8,
				padding: "6px 10px",
				fontSize: 12,
				cursor: "pointer",
			}}
		>
			{label}
		</button>
	);
}

export function NarrativeEditor() {
	const editorRef = useRef<HTMLDivElement | null>(null);
	const ide = useNarrativeIde();
	const timelineEvents = Array.isArray(ide.lastResult?.events) ? ide.lastResult.events : [];
	const timelineConflicts = ide.lastResult?.timeline?.conflicts || [];

	return (
		<div
			style={{
				minHeight: "100vh",
				background: "radial-gradient(circle at 20% 0%, #253957 0%, #101722 48%, #0a0f16 100%)",
				color: "#eff5ff",
				padding: 16,
				boxSizing: "border-box",
				fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif",
			}}
		>
			<header
				style={{
					marginBottom: 12,
					background: "linear-gradient(90deg, #20314d 0%, #172133 100%)",
					border: "1px solid #334a70",
					borderRadius: 14,
					padding: 12,
					display: "grid",
					gap: 10,
				}}
			>
				<div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
					<h1 style={{ margin: 0, fontSize: 20 }}>Narrative IDE</h1>
					<div style={{ display: "flex", gap: 8, alignItems: "center" }}>
						<span style={{ fontSize: 12, color: "#9ab1da" }}>
							{ide.isChecking ? "Live checking..." : "Live check idle"}
						</span>
						<button
							type="button"
							onClick={() => void ide.runPipeline()}
							disabled={ide.isRunning}
							style={{
								border: "1px solid #3d72ff",
								background: ide.isRunning ? "#27479f" : "#3564dd",
								color: "white",
								borderRadius: 8,
								padding: "8px 14px",
								cursor: ide.isRunning ? "not-allowed" : "pointer",
								fontWeight: 700,
								fontSize: 12,
							}}
						>
							{ide.isRunning ? "Running Pipeline..." : "Run Scene"}
						</button>
					</div>
				</div>

				<input
					value={ide.sceneTitle}
					onChange={(event) => ide.setSceneTitle(event.target.value)}
					placeholder="Scene title"
					style={{
						background: "#121a2a",
						color: "#e8f0ff",
						border: "1px solid #324666",
						borderRadius: 10,
						padding: "10px 12px",
						fontSize: 13,
					}}
				/>

				<GatePanel result={ide.lastResult} isRunning={ide.isRunning} />
			</header>

			<div
				style={{
					display: "grid",
					gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
					gap: 12,
					alignItems: "start",
				}}
			>
				<div style={{ display: "grid", gap: 12 }}>
					<PBKDLab />
					<WorldPanel memory={ide.lastResult?.memory?.retrieved || null} />
					<CharacterPanel characterState={ide.lastResult?.memory?.character_state || {}} />
				</div>

				<main style={{ display: "grid", gap: 12 }}>
					<section
						style={{
							border: "1px solid #344765",
							background: "linear-gradient(180deg, #131d2e 0%, #0f1624 100%)",
							borderRadius: 14,
							padding: 10,
						}}
					>
						<div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
							<ToolbarButton label="Bold" onClick={() => ide.applyFormatting("bold")} />
							<ToolbarButton label="Italic" onClick={() => ide.applyFormatting("italic")} />
							<ToolbarButton label="Underline" onClick={() => ide.applyFormatting("underline")} />
							<ToolbarButton label="Bullet" onClick={() => ide.applyFormatting("insertUnorderedList")} />
							<button
								type="button"
								onClick={ide.clearIssues}
								style={{
									border: "1px solid #5a3e54",
									background: "#2b1b2a",
									color: "#f8d9ea",
									borderRadius: 8,
									padding: "6px 10px",
									fontSize: 12,
									marginLeft: "auto",
									cursor: "pointer",
								}}
							>
								Clear Problems
							</button>
						</div>

						<div
							ref={editorRef}
							contentEditable
							suppressContentEditableWarning
							onInput={(event) => ide.setEditorHtml(event.currentTarget.innerHTML)}
							dangerouslySetInnerHTML={{ __html: ide.editorHtml }}
							style={{
								minHeight: 280,
								border: "1px solid #2f4363",
								borderRadius: 10,
								background: "#0c121d",
								color: "#e4edff",
								padding: 14,
								lineHeight: 1.6,
								fontSize: 14,
								outline: "none",
							}}
						/>

						{ide.errorMessage && (
							<div style={{ marginTop: 8, color: "#ffb7b7", fontSize: 12 }}>
								Failed to run: {ide.errorMessage}
							</div>
						)}
					</section>

					<TimelineView
						events={timelineEvents}
						conflicts={timelineConflicts}
					/>

					<RelationshipGraph edges={ide.relationshipEdges} />
				</main>

				<ConsistencySidebar
					issues={ide.issues}
					selectedIssueId={ide.selectedIssueId}
					onSelectIssue={ide.setSelectedIssueId}
				/>
			</div>
		</div>
	);
}

export default NarrativeEditor;
