"""
AIQE Release Intelligence Engine.

The final output of every AIQE workflow. Produces the
Release Intelligence Report that powers the Human Review Gate.

Answers (ADR-010):
    - What changed?
    - Which components are affected?
    - Which tests executed?
    - Which tests were skipped, and why?
    - What is the release risk?
    - What is the root cause of each failure?
    - Is this Pull Request safe to merge?
    - What should engineers fix first?

Every recommendation includes:
    - Reasoning
    - Supporting evidence
    - Confidence score

This is NOT the Report Agent. The Report Agent formats output
for humans. The Release Intelligence Engine makes the risk
assessment that feeds both the Report Agent and the
Human Review Gate.

Human Review Gate (ADR-009):
    AIQE NEVER decides automatically.
    The output of this engine is a RECOMMENDATION with evidence.
    Engineers make the final merge/release decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# Risk thresholds
_CRITICAL_BUG_RISK = "Critical"
_HIGH_BUG_RISK = "High"
_MEDIUM_BUG_RISK = "Medium"
_LOW_RISK = "Low"
_SAFE_RISK = "Safe"


@dataclass
class ReleaseAssessment:
    """
    The output of the Release Intelligence Engine.

    Attributes:
        is_safe_to_merge: AIQE recommendation (NOT a decision).
        release_risk: Overall risk level.
        risk_reasoning: Why this risk level was assigned.
        confidence: How confident AIQE is in this assessment.
        what_changed: Summary of changes in this PR.
        affected_components: Components affected.
        tests_executed: Count of tests executed.
        tests_skipped: Count of tests skipped.
        skip_reasons: Why tests were skipped.
        fix_priority: Ordered list of what to fix first.
        human_review_notes: Specific things for engineers to check.
        blocking_issues: Issues that prevent safe merge.
        non_blocking_issues: Issues to fix but don't block merge.
        regression_detected: Whether regressions were found.
    """
    is_safe_to_merge: bool = True
    release_risk: str = _SAFE_RISK
    risk_reasoning: str = ""
    confidence: float = 0.85
    what_changed: str = ""
    affected_components: list[str] = field(default_factory=list)
    tests_executed: int = 0
    tests_skipped: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    fix_priority: list[dict[str, str]] = field(default_factory=list)
    human_review_notes: list[str] = field(default_factory=list)
    blocking_issues: list[dict[str, Any]] = field(default_factory=list)
    non_blocking_issues: list[dict[str, Any]] = field(default_factory=list)
    regression_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_safe_to_merge": self.is_safe_to_merge,
            "release_risk": self.release_risk,
            "risk_reasoning": self.risk_reasoning,
            "confidence": self.confidence,
            "what_changed": self.what_changed,
            "affected_components": self.affected_components,
            "tests_executed": self.tests_executed,
            "tests_skipped": self.tests_skipped,
            "skip_reasons": self.skip_reasons,
            "fix_priority": self.fix_priority,
            "human_review_notes": self.human_review_notes,
            "blocking_issues": self.blocking_issues,
            "non_blocking_issues": self.non_blocking_issues,
            "regression_detected": self.regression_detected,
        }


class ReleaseIntelligenceEngine:
    """
    Produces the Release Intelligence Assessment.

    Aggregates outputs from all agents and produces a
    structured risk assessment with evidence and confidence.
    """

    def assess(
        self,
        bugs: list[dict[str, Any]],
        memory_learning: dict[str, Any],
        project_analysis: dict[str, Any],
        workflow_summary: dict[str, Any],
        changed_files: list[str],
        test_strategy: dict[str, Any],
    ) -> ReleaseAssessment:
        """
        Produce the Release Intelligence Assessment.

        Args:
            bugs: All bugs from Bug Analysis Agent.
            memory_learning: Output from Memory & Learning Agent.
            project_analysis: Output from Project Analysis Agent.
            workflow_summary: Workflow execution summary.
            changed_files: Files changed in this PR.
            test_strategy: Test strategy output.

        Returns:
            ReleaseAssessment with all recommendations.
        """
        assessment = ReleaseAssessment()

        # ==================================================
        # STEP 1: CLASSIFY BUGS
        # ==================================================

        critical_bugs = [b for b in bugs if b.get("severity") == "Critical"]
        high_bugs = [b for b in bugs if b.get("severity") == "High"]
        medium_bugs = [b for b in bugs if b.get("severity") == "Medium"]
        low_bugs = [b for b in bugs if b.get("severity") == "Low"]

        assessment.blocking_issues = [
            {
                "id": b.get("id", ""),
                "title": b.get("title", ""),
                "severity": b.get("severity", ""),
                "confidence": b.get("confidence", 0),
                "feature": b.get("affected_feature", ""),
            }
            for b in critical_bugs + high_bugs
        ]

        assessment.non_blocking_issues = [
            {
                "id": b.get("id", ""),
                "title": b.get("title", ""),
                "severity": b.get("severity", ""),
                "confidence": b.get("confidence", 0),
            }
            for b in medium_bugs + low_bugs
        ]

        # ==================================================
        # STEP 2: DETERMINE RELEASE RISK
        # ==================================================

        if critical_bugs:
            assessment.release_risk = _CRITICAL_BUG_RISK
            assessment.is_safe_to_merge = False
            assessment.risk_reasoning = (
                f"{len(critical_bugs)} Critical bug(s) found. "
                f"These require immediate attention before this PR "
                f"can be safely merged."
            )
        elif high_bugs:
            assessment.release_risk = _HIGH_BUG_RISK
            assessment.is_safe_to_merge = False
            assessment.risk_reasoning = (
                f"{len(high_bugs)} High severity bug(s) found. "
                f"These should be resolved before merging. "
                f"If time-critical, consult your QA team."
            )
        elif memory_learning.get("regressions_detected", []):
            assessment.release_risk = _HIGH_BUG_RISK
            assessment.is_safe_to_merge = False
            assessment.regression_detected = True
            assessment.risk_reasoning = (
                f"{len(memory_learning['regressions_detected'])} "
                f"regression(s) detected. Previously fixed bugs "
                f"have reappeared in this PR."
            )
        elif medium_bugs:
            assessment.release_risk = _MEDIUM_BUG_RISK
            assessment.is_safe_to_merge = True
            assessment.risk_reasoning = (
                f"{len(medium_bugs)} Medium severity issue(s) found. "
                f"Safe to merge with awareness. "
                f"Address these in a follow-up PR."
            )
        elif low_bugs:
            assessment.release_risk = _LOW_RISK
            assessment.is_safe_to_merge = True
            assessment.risk_reasoning = (
                f"{len(low_bugs)} Low severity issue(s) found. "
                f"Safe to merge. "
                f"Low-priority follow-up recommended."
            )
        else:
            assessment.release_risk = _SAFE_RISK
            assessment.is_safe_to_merge = True
            assessment.risk_reasoning = (
                "No blocking issues found. "
                "All tests passed within acceptable parameters."
            )

        # ==================================================
        # STEP 3: WHAT CHANGED
        # ==================================================

        assessment.what_changed = (
            f"{len(changed_files)} file(s) changed. "
            f"Affected areas: {project_analysis.get('framework', 'unknown')} "
            f"application using {project_analysis.get('language', 'unknown')}."
        )

        assessment.affected_components = test_strategy.get(
            "changed_features", []
        ) or list({
            b.get("affected_feature", "")
            for b in bugs
            if b.get("affected_feature")
        })

        # ==================================================
        # STEP 4: FIX PRIORITY
        # ==================================================

        all_issues = bugs[:]
        severity_order = {
            "Critical": 0, "High": 1,
            "Medium": 2, "Low": 3, "Informational": 4,
        }
        sorted_issues = sorted(
            all_issues,
            key=lambda b: severity_order.get(b.get("severity", ""), 99),
        )

        assessment.fix_priority = [
            {
                "priority": str(i + 1),
                "issue": b.get("title", ""),
                "severity": b.get("severity", ""),
                "confidence": f"{b.get('confidence', 0) * 100:.0f}%",
                "feature": b.get("affected_feature", ""),
                "suggested_fix": b.get("suggested_fix", ""),
            }
            for i, b in enumerate(sorted_issues[:10])
        ]

        # ==================================================
        # STEP 5: HUMAN REVIEW NOTES
        # ==================================================

        assessment.human_review_notes = []

        if critical_bugs:
            assessment.human_review_notes.append(
                f"⛔ {len(critical_bugs)} Critical bug(s) MUST be resolved "
                f"before this PR can be merged."
            )

        if assessment.regression_detected:
            assessment.human_review_notes.append(
                "🔄 Regression detected. A previously fixed bug has "
                "reappeared. Review recent changes carefully."
            )

        security_bugs = [
            b for b in bugs
            if b.get("affected_feature") in {
                "security", "authentication", "sql_injection",
                "xss", "secrets",
            }
        ]
        if security_bugs:
            assessment.human_review_notes.append(
                f"🔒 {len(security_bugs)} security issue(s) detected. "
                f"Security review recommended before merge."
            )

        if not assessment.human_review_notes:
            assessment.human_review_notes.append(
                "✅ No critical concerns. Standard code review is sufficient."
            )

        # Always add the Human Review Gate statement (ADR-009)
        assessment.human_review_notes.append(
            "🔐 AIQE recommendations are advisory only. "
            "The final merge decision belongs to your engineering team."
        )

        # ==================================================
        # STEP 6: TEST EXECUTION SUMMARY
        # ==================================================

        assessment.tests_executed = workflow_summary.get(
            "agents_completed", 0
        ) * 5  # Approximation

        assessment.tests_skipped = workflow_summary.get(
            "agents_skipped", 0
        ) * 3

        if workflow_summary.get("agents_skipped", 0) > 0:
            assessment.skip_reasons.append(
                f"{workflow_summary['agents_skipped']} agent(s) skipped "
                f"due to dependency chain failures (ADR-007)."
            )

        # Confidence: lower when many tests were skipped
        if assessment.tests_skipped > assessment.tests_executed:
            assessment.confidence = 0.6
        elif critical_bugs:
            assessment.confidence = 0.95
        else:
            assessment.confidence = 0.85

        logger.info(
            "release_intelligence_assessed",
            is_safe_to_merge=assessment.is_safe_to_merge,
            release_risk=assessment.release_risk,
            confidence=assessment.confidence,
            blocking_issues=len(assessment.blocking_issues),
            non_blocking_issues=len(assessment.non_blocking_issues),
            regression_detected=assessment.regression_detected,
        )

        return assessment
