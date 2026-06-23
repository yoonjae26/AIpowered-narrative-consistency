import { NarrativeMutationResponse } from "../../stores";

type Props = {
	result: NarrativeMutationResponse | null;
	isRunning: boolean;
};

function decisionStyle(decision: string) {
	if (decision === "approve") {
		return {
			label: "APPROVE",
			background: "#1f4f37",
			border: "#2f8b5f",
			color: "#b9f6d3",
		};
	}
	if (decision === "needs-override") {
		return {
			label: "NEEDS OVERRIDE",
			background: "#5c4016",
			border: "#a06f1f",
			color: "#ffe0a4",
		};
	}
	if (decision === "reject") {
		return {
			label: "REJECT",
			background: "#5a2121",
			border: "#9e3333",
			color: "#ffc3c3",
		};
	}
	return {
		label: "NO DECISION",
		background: "#24314d",
		border: "#4f6696",
		color: "#d4e2ff",
	};
}

export function GatePanel({ result, isRunning }: Props) {
	const decision = result?.gate?.decision || result?.decision || "";
	const style = decisionStyle(decision);
	const blocking = result?.gate?.blocking_reasons || [];
	const overrideable = result?.gate?.overrideable_reasons || [];
	const preflight = result?.preflight;

	return (
		<section
			style={{
				background: "linear-gradient(125deg, #16263f 0%, #121b2b 100%)",
				border: "1px solid #304b70",
				borderRadius: 12,
				padding: 10,
				display: "grid",
				gap: 8,
			}}
		>
			<div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
				<div style={{ fontSize: 12, color: "#9db6de", fontWeight: 700 }}>Pre-Persist Gate</div>
				<span
					style={{
						fontSize: 11,
						fontWeight: 800,
						padding: "3px 10px",
						borderRadius: 999,
						background: style.background,
						border: `1px solid ${style.border}`,
						color: style.color,
					}}
				>
					{isRunning ? "EVALUATING" : style.label}
				</span>
			</div>

			<div style={{ fontSize: 12, color: "#d7e5ff" }}>
				{result?.gate?.message || result?.error || "Run Scene to evaluate approve/reject/needs-override decision."}
			</div>

			{!!preflight && (
				<div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 6 }}>
					<div style={{ fontSize: 11, color: "#90a8d1" }}>
						Consistency errors: <strong style={{ color: "#e7efff" }}>{preflight.consistency?.error_count ?? 0}</strong>
					</div>
					<div style={{ fontSize: 11, color: "#90a8d1" }}>
						Semantic issues: <strong style={{ color: "#e7efff" }}>{preflight.semantic_issue_count ?? 0}</strong>
					</div>
					<div style={{ fontSize: 11, color: "#90a8d1" }}>
						Canon conflicts: <strong style={{ color: "#e7efff" }}>{preflight.canon_conflict_count ?? 0}</strong>
					</div>
					<div style={{ fontSize: 11, color: "#90a8d1" }}>
						Timeline valid: <strong style={{ color: "#e7efff" }}>{preflight.timeline?.valid ? "yes" : "no"}</strong>
					</div>
				</div>
			)}

			{(blocking.length > 0 || overrideable.length > 0) && (
				<div style={{ display: "grid", gap: 6 }}>
					{blocking.slice(0, 4).map((message, index) => (
						<div
							key={`block-${index}`}
							style={{
								fontSize: 11,
								padding: "7px 9px",
								borderRadius: 8,
								border: "1px solid #5e3030",
								background: "#281618",
								color: "#ffc4c4",
							}}
						>
							{message}
						</div>
					))}
					{overrideable.slice(0, 4).map((message, index) => (
						<div
							key={`override-${index}`}
							style={{
								fontSize: 11,
								padding: "7px 9px",
								borderRadius: 8,
								border: "1px solid #7f642d",
								background: "#2d2414",
								color: "#ffe2ab",
							}}
						>
							{message}
						</div>
					))}
				</div>
			)}
		</section>
	);
}

export default GatePanel;
