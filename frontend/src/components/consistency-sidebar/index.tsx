import { NarrativeIssue } from "../../stores";

type Props = {
	issues: NarrativeIssue[];
	selectedIssueId: string | null;
	onSelectIssue: (issueId: string) => void;
};

const severityIcon: Record<string, string> = {
	error: "E",
	warning: "W",
	info: "i",
};

function SeverityBadge({ severity }: { severity: string }) {
	const background = severity === "error" ? "#551d1d" : severity === "warning" ? "#5b4412" : "#1f3d5f";
	const color = severity === "error" ? "#ffb5b5" : severity === "warning" ? "#ffd78b" : "#95d8ff";
	return (
		<span
			style={{
				display: "inline-flex",
				alignItems: "center",
				gap: 6,
				background,
				color,
				padding: "2px 8px",
				borderRadius: 999,
				fontSize: 11,
				fontWeight: 700,
			}}
		>
			<span>{severityIcon[severity] || "i"}</span>
			<span>{severity.toUpperCase()}</span>
		</span>
	);
}

export function ConsistencySidebar({ issues, selectedIssueId, onSelectIssue }: Props) {
	const errorCount = issues.filter((item) => item.severity === "error").length;
	const warningCount = issues.filter((item) => item.severity === "warning").length;
	const selected = issues.find((item) => item.id === selectedIssueId) || null;

	return (
		<aside
			style={{
				height: "100%",
				background: "linear-gradient(180deg, #1b1f2a 0%, #12151d 100%)",
				border: "1px solid #2e3444",
				borderRadius: 14,
				overflow: "hidden",
				display: "flex",
				flexDirection: "column",
			}}
		>
			<header
				style={{
					padding: "12px 14px",
					borderBottom: "1px solid #2a3140",
					display: "flex",
					justifyContent: "space-between",
					alignItems: "center",
					color: "#dfe7ff",
					fontWeight: 700,
				}}
			>
				<span>Consistency Problems</span>
				<span style={{ fontSize: 12, color: "#93a0c2" }}>{errorCount} errors, {warningCount} warnings</span>
			</header>

			<div style={{ overflowY: "auto", padding: 8, display: "grid", gap: 8, flex: 1 }}>
				{issues.length === 0 && (
					<div
						style={{
							fontSize: 13,
							color: "#8f9cb8",
							border: "1px dashed #33415f",
							borderRadius: 10,
							padding: 12,
						}}
					>
						No issues detected. Live checks will show up here.
					</div>
				)}

				{issues.map((issue) => {
					const active = issue.id === selectedIssueId;
					return (
						<button
							type="button"
							key={issue.id}
							onClick={() => onSelectIssue(issue.id)}
							style={{
								textAlign: "left",
								border: active ? "1px solid #79a8ff" : "1px solid #2d364b",
								background: active ? "#1e2b45" : "#141926",
								color: "#e8eeff",
								borderRadius: 10,
								padding: 10,
								cursor: "pointer",
								display: "grid",
								gap: 6,
							}}
						>
							<div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
								<SeverityBadge severity={issue.severity} />
								<span style={{ fontSize: 11, color: "#95a4c7" }}>{issue.source}</span>
							</div>
							<div style={{ fontWeight: 600, fontSize: 13 }}>{issue.message}</div>
							<div style={{ fontSize: 11, color: "#9ba9c8" }}>{issue.code}</div>
						</button>
					);
				})}
			</div>

			<div
				style={{
					borderTop: "1px solid #2a3140",
					padding: 10,
					background: "#101521",
				}}
			>
				<div style={{ fontSize: 11, color: "#8fa1c6", textTransform: "uppercase", letterSpacing: 0.3 }}>
					Problem Details
				</div>
				{selected ? (
					<div style={{ marginTop: 6, display: "grid", gap: 6 }}>
						<div style={{ fontSize: 13, color: "#e6eeff", fontWeight: 700 }}>{selected.message}</div>
						<div style={{ fontSize: 12, color: "#9baad0" }}>Code: {selected.code}</div>
						{selected.suggestion && <div style={{ fontSize: 12, color: "#b7c7e8" }}>Hint: {selected.suggestion}</div>}
					</div>
				) : (
					<div style={{ marginTop: 6, fontSize: 12, color: "#8092b7" }}>Select an item to inspect details.</div>
				)}
			</div>
		</aside>
	);
}

export default ConsistencySidebar;
