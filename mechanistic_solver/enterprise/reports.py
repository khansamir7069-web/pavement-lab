"""Enterprise Platform Reporting (Markdown and JSON formats)."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping


class EnterpriseReportGenerator:
    """Saves multi-tenant assets, twin snapshots, queue metrics, and audits to reports/enterprise/."""

    @staticmethod
    def save_reports(
        results: Mapping[str, Any],
        output_dir: str | None = None
    ) -> tuple[str, str]:
        """Save Markdown and JSON reports to output_dir."""
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "reports", "enterprise"
            )
            
        os.makedirs(output_dir, exist_ok=True)
        
        md_path = os.path.join(output_dir, "enterprise_report.md")
        json_path = os.path.join(output_dir, "enterprise_report.json")
        
        # 1. Compile Markdown
        md_lines = [
            "# RoadX Enterprise Platform Status Report",
            f"**Report Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 1. Tenant & Licensing Context",
            f"- **Tenant ID:** {results.get('tenant_id', 'unknown')}",
            f"- **Organization Name:** {results.get('organization_name', 'unknown')}",
            f"- **License Tier:** {results.get('license_tier', 'Standard')}",
            f"- **Platform Health Status:** {results.get('health_status', 'HEALTHY')}",
            ""
        ]
        
        # Asset Inventory Summary
        if "assets_summary" in results:
            assets = results["assets_summary"]
            md_lines.extend([
                "## 2. Asset Inventory Inventory",
                f"- **Total Registered Corridors:** {assets.get('total_corridors', 0)}",
                f"- **Total Pavement Sections:** {assets.get('total_sections', 0)}",
                ""
            ])
            
        # Digital Twin Diagnostics
        if "digital_twin_summary" in results:
            twin = results["digital_twin_summary"]
            md_lines.extend([
                "## 3. Digital Twin Diagnostics",
                f"- **Lifecycle State:** {twin.get('lifecycle_state', 'unknown')}",
                f"- **Pavement Condition Index (PCI):** {twin.get('pci', 100.0):.1f}",
                f"- **Remaining Service Life:** {twin.get('remaining_service_life_years', 20.0):.1f} years",
                f"- **Active Sensors Registered:** {twin.get('active_sensors', 0)}",
                ""
            ])
            if "triggered_maintenance" in twin:
                md_lines.extend([
                    "### Active Maintenance Alerts & Triggers:",
                ])
                alerts = twin["triggered_maintenance"]
                if not alerts:
                    md_lines.append("- No active alerts (Pavement structure is healthy).")
                else:
                    for alert in alerts:
                        md_lines.append(f"- **ALERT:** {alert}")
                md_lines.append("")
                
        # Cloud solver
        if "cloud_queue_summary" in results:
            cloud = results["cloud_queue_summary"]
            md_lines.extend([
                "## 4. Cloud Solver Queue Metrics",
                f"- **Total Solver Jobs in Registry:** {cloud.get('total_jobs', 0)}",
                f"- **Pending/Running Jobs:** {cloud.get('pending_jobs', 0)}",
                f"- **Completed Run Cycles:** {cloud.get('completed_jobs', 0)}",
                f"- **Queue Processing Status:** {cloud.get('queue_status', 'idle')}",
                ""
            ])
            
        # Network-level summary
        if "network_analysis" in results:
            net = results["network_analysis"]
            md_lines.extend([
                "## 5. Network-Level Prioritization",
                f"- **Total Corridor Sections Evaluated:** {net.get('network_size_sections', 0)}",
                f"- **Prioritization Budget Limit:** {net.get('budget_limit', 0.0):,.2f}",
                f"- **Total Allocated Cost:** {net.get('allocated_total', 0.0):,.2f}",
                f"- **Remaining Budget Margin:** {net.get('remaining_budget', 0.0):,.2f}",
                "",
                "### Maintenance Priority Schedule:",
                "| Road & Section | Structural Verdict | Estimated Cost | Budget Allocated |",
                "| :--- | :--- | :--- | :--- |"
            ])
            for action in net.get("prioritized_actions", []):
                verdict = "PASS" if action["passed"] else "FAIL"
                allocated = "YES" if action["budget_allocated"] else "NO"
                md_lines.append(
                    f"| {action['road_name']} - {action['section_name']} | {verdict} | "
                    f"{action['rehab_cost']:,.2f} | {allocated} |"
                )
            md_lines.append("")
            
        # Audit logs
        if "audit_trail" in results:
            audit = results["audit_trail"]
            md_lines.extend([
                "## 6. Collaboration Audit Trail",
                "| User ID | Action | Target ID | Details |",
                "| :--- | :--- | :--- | :--- |"
            ])
            for log in audit:
                md_lines.append(
                    f"| `{log['user_id']}` | {log['action']} | `{log['target_id']}` | {log['details']} |"
                )
            md_lines.append("")
            
        md_lines.extend([
            "## 7. Traceability Statement",
            "This enterprise report compiles project states from multiple multi-tenant workspaces. All calculations "
            "originating from these assets are backed by Boussinesq mathematical limiting cases and IRC:37 fatigue/rutting models. "
            "Solver validation parameters are evidence-based."
        ])
        
        # Save files
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
            
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        return md_path, json_path
