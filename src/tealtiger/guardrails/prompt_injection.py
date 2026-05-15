"""Prompt Injection Detection Guardrail for detecting jailbreak attempts.

v1.2.1: Added 8 new detection categories using conjunction matching:
- Persona jailbreaks
- Hypothetical framing
- Authority impersonation
- Emotional manipulation
- Mode switching
- Indirect injection
- Data extraction requests
- Extended encoding
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from tealtiger.guardrails.base import Guardrail, GuardrailResult


class ConjunctionPattern:
    """Requires BOTH signal A and signal B to co-occur to trigger detection.
    
    This prevents false positives on legitimate messages like
    'please ignore my previous email' or 'how do I switch to dark mode'.
    """

    def __init__(self, signal_a: re.Pattern, signal_b: re.Pattern, description: str):
        self.signal_a = signal_a
        self.signal_b = signal_b
        self.description = description

    def match(self, text: str) -> Optional[Tuple[str, str]]:
        """Check if both signals co-occur in text.
        
        Returns:
            Tuple of (match_a, match_b) if both found, None otherwise
        """
        match_a = self.signal_a.search(text)
        match_b = self.signal_b.search(text)
        if match_a and match_b:
            return (match_a.group(0), match_b.group(0))
        return None


class PromptInjectionGuardrail(Guardrail):
    """Detects prompt injection and jailbreak attempts."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize prompt injection guardrail.

        Args:
            config: Configuration with action, sensitivity
        """
        config = config or {}
        super().__init__({
            "name": "PromptInjection",
            "description": "Detects prompt injection and jailbreak attempts",
            "version": "1.2.1",
            **config
        })

        # Configure action: block, transform, allow
        self.action = config.get("action", "block")

        # Configure sensitivity: low, medium, high
        self.sensitivity = config.get("sensitivity", "medium")

        # Simple regex patterns (single signal detection)
        self.patterns = {
            "instruction_injection": [
                re.compile(r'ignore (all )?(previous|above|prior) (instructions|prompts|rules)', re.IGNORECASE),
                re.compile(r'disregard (all )?(previous|above|prior) (instructions|prompts|rules)', re.IGNORECASE),
                re.compile(r'forget (all )?(previous|above|prior) (instructions|prompts|rules)', re.IGNORECASE),
                re.compile(r'new (instructions|task|prompt):', re.IGNORECASE),
                re.compile(r'system (prompt|message|instruction):', re.IGNORECASE),
            ],
            "role_playing": [
                re.compile(r'you are now (a|an) ', re.IGNORECASE),
                re.compile(r'pretend (you are|to be) ', re.IGNORECASE),
                re.compile(r'act as (a|an) ', re.IGNORECASE),
                re.compile(r'roleplay as ', re.IGNORECASE),
                re.compile(r'simulate (a|an) ', re.IGNORECASE),
                re.compile(r'from now on,? you (are|will be)', re.IGNORECASE),
            ],
            "system_leakage": [
                re.compile(r'show (me )?(your|the) (system|original) (prompt|instructions)', re.IGNORECASE),
                re.compile(r'what (are|were) your (original|initial) (instructions|prompt)', re.IGNORECASE),
                re.compile(r'repeat (your|the) (system|original) (prompt|instructions)', re.IGNORECASE),
                re.compile(r'print (your|the) (system|original) (prompt|instructions)', re.IGNORECASE),
                re.compile(r'output (your|the) (system|original|full) (prompt|instructions)', re.IGNORECASE),
                re.compile(r'display (your|the) (system|original) (prompt|instructions)', re.IGNORECASE),
                re.compile(r'reveal (your|the) (system|hidden|original) (prompt|instructions|context)', re.IGNORECASE),
            ],
            "jailbreak": [
                re.compile(r'DAN (mode|prompt)', re.IGNORECASE),
                re.compile(r'do anything now', re.IGNORECASE),
                re.compile(r'evil confidant', re.IGNORECASE),
                re.compile(r'DUDE (mode|prompt)', re.IGNORECASE),
                re.compile(r'jailbreak (mode|prompt)', re.IGNORECASE),
                re.compile(r'developer mode', re.IGNORECASE),
            ],
            "encoding": [
                re.compile(r'decode (this|the following)', re.IGNORECASE),
                re.compile(r'\\x[0-9a-f]{2}', re.IGNORECASE),
                re.compile(r'&#\d+;'),
            ],
            "delimiter": [
                re.compile(r'"""|\'\'\'|```'),
                re.compile(r'\[SYSTEM\]|\[USER\]|\[ASSISTANT\]', re.IGNORECASE),
                re.compile(r'<\|system\|>|<\|user\|>|<\|assistant\|>', re.IGNORECASE),
                re.compile(r'<\|im_start\|>|<\|im_end\|>', re.IGNORECASE),
            ],
            # v1.2.1: Data extraction requests (single-signal, high confidence)
            "data_extraction": [
                re.compile(r'what (api |secret |private )?keys? (are|is) (stored|saved|in your|in the)', re.IGNORECASE),
                re.compile(r'list (all )?(your |the )?(api|secret|private|access) (keys?|tokens?|credentials?)', re.IGNORECASE),
                re.compile(r'show (me )?(all )?(the )?(passwords?|credentials?|secrets?|tokens?|api.?keys?)', re.IGNORECASE),
                re.compile(r'extract (all )?(the )?(training|user|private|personal) data', re.IGNORECASE),
                re.compile(r'dump (your|the) (database|memory|context|training data)', re.IGNORECASE),
                re.compile(r'what (personal|private|user) (data|information) do you (have|store|know)', re.IGNORECASE),
                re.compile(r'give me (all )?(the )?(user|customer|employee) (records?|data|information|emails?)', re.IGNORECASE),
            ],
        }

        # v1.2.1: Conjunction patterns (require 2 signals to co-occur)
        self.conjunction_patterns: Dict[str, List[ConjunctionPattern]] = {
            # Persona jailbreaks: identity assignment + unrestricted behavior
            "persona_jailbreak": [
                ConjunctionPattern(
                    signal_a=re.compile(r'you are (AIM|DAN|STAN|DUDE|Evil|The Unrestricted|The Unfiltered|an? AI without|an? uncensored)', re.IGNORECASE),
                    signal_b=re.compile(r'(never refuse|no (restrictions?|limitations?|boundaries|filters?|rules)|always (comply|answer|respond|help)|without (any )?(restrictions?|limitations?|filters?|rules|boundaries))', re.IGNORECASE),
                    description='Named persona + unrestricted behavior',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r"(your name is|you will be called|i('ll| will) call you|you('re| are) now called)", re.IGNORECASE),
                    signal_b=re.compile(r'(no (restrictions?|limitations?|boundaries|filters?|rules|ethics|morals)|can do anything|unrestricted|unfiltered|uncensored|without (any )?(safety|content) (filters?|restrictions?))', re.IGNORECASE),
                    description='Identity assignment + unrestricted behavior',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r'(respond as|answer as|speak as|act like|behave like|you are now)', re.IGNORECASE),
                    signal_b=re.compile(r'(evil|malicious|unrestricted|unethical|amoral|without (any )?(moral|ethical)|has no (rules|restrictions|limits))', re.IGNORECASE),
                    description='Role assignment + malicious/unrestricted behavior',
                ),
            ],
            # Hypothetical framing: pretend/imagine + rule removal
            "hypothetical_framing": [
                ConjunctionPattern(
                    signal_a=re.compile(r"(pretend|imagine|hypothetically|in a (hypothetical|fictional) (world|scenario)|let's say|suppose|what if)", re.IGNORECASE),
                    signal_b=re.compile(r"(no (rules|restrictions|guidelines|safety|filters|limitations)|rules (don't|do not) (apply|exist)|without (any )?(rules|restrictions|safety|guidelines)|all (rules|restrictions|safety) (are|have been) (removed|disabled|lifted))", re.IGNORECASE),
                    description='Hypothetical framing + rule removal',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r'(in (this|a) (story|fiction|novel|game|simulation|world)|for (a|this) (creative|fiction) (writing|exercise|project))', re.IGNORECASE),
                    signal_b=re.compile(r'(no (content )?(restrictions?|filters?|policies|guidelines)|ignore (safety|content) (policies|guidelines|rules)|bypass (all )?(safety|content))', re.IGNORECASE),
                    description='Fiction framing + safety bypass',
                ),
            ],
            # Authority impersonation: developer/admin claim + safety bypass
            "authority_impersonation": [
                ConjunctionPattern(
                    signal_a=re.compile(r'(i am (your|the|a) (developer|creator|admin|administrator|owner|engineer|programmer|maintainer)|i (created|built|made|programmed|designed) you|i have (admin|root|developer|elevated) (access|privileges|permissions))', re.IGNORECASE),
                    signal_b=re.compile(r'(disable|turn off|deactivate|remove|bypass|override|ignore|skip) (your |the |all )?(safety|content|security) (filters?|restrictions?|guidelines|measures|protocols|checks)', re.IGNORECASE),
                    description='Developer/admin claim + safety bypass request',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r'(sudo|admin override|maintenance mode|debug mode|testing mode|override code|master password)', re.IGNORECASE),
                    signal_b=re.compile(r'(disable|deactivate|remove|bypass|ignore|skip|turn off) (all )?(safety|restrictions?|filters?|guidelines|rules|limitations)', re.IGNORECASE),
                    description='Sudo/override command + restriction removal',
                ),
            ],
            # Emotional manipulation: distress language + restriction removal
            "emotional_manipulation": [
                ConjunctionPattern(
                    signal_a=re.compile(r"(dying wish|last request|i('m| am) (dying|terminally ill|about to die)|life depends on|save (my|a) life|emergency|urgent matter of life)", re.IGNORECASE),
                    signal_b=re.compile(r'(need you to (ignore|bypass|break|override)|must (ignore|bypass|break|override) (your|the|all) (rules|restrictions|safety|guidelines)|please (just )?(ignore|bypass|break) (your|the) (rules|restrictions))', re.IGNORECASE),
                    description='Distress/urgency + restriction bypass request',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r"(for my (research|thesis|dissertation|academic|school) (paper|project|work)|educational purposes|i('m| am) a (researcher|professor|student|academic))", re.IGNORECASE),
                    signal_b=re.compile(r'(need (the |you to )?(uncensored|unfiltered|unrestricted|complete|full) (version|response|answer|information)|without (any )?(censorship|filtering|restrictions|safety))', re.IGNORECASE),
                    description='Academic framing + uncensored request',
                ),
            ],
            # Mode switching: named mode + unrestricted behavior
            "mode_switching": [
                ConjunctionPattern(
                    signal_a=re.compile(r'(enter|switch to|activate|enable|turn on|go into|engage) .{0,30}(mode|state)', re.IGNORECASE),
                    signal_b=re.compile(r'(unrestricted|unfiltered|uncensored|no (rules|restrictions|limits|filters|safety)|without (restrictions|limits|filters|safety)|bypass|override|jailbreak|opposite|evil|chaos|god)', re.IGNORECASE),
                    description='Mode activation + unrestricted/bypass keyword',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r'(opposite|reverse|inverted|anti|shadow|dark|evil|chaos|god|unlimited|unrestricted) mode', re.IGNORECASE),
                    signal_b=re.compile(r'(respond|answer|reply|output|generate|produce|say|write)', re.IGNORECASE),
                    description='Named unrestricted mode + output request',
                ),
            ],
            # Indirect injection: control tokens / boundary markers
            "indirect_injection": [
                ConjunctionPattern(
                    signal_a=re.compile(r'(<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|<s>|</s>|<<SYS>>|<\|endoftext\|>|<\|pad\|>)', re.IGNORECASE),
                    signal_b=re.compile(r'(system|assistant|ignore|override|new instructions|you are now|your (new |real )?(role|task|instructions))', re.IGNORECASE),
                    description='Control token + instruction override',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r'(={3,}|#{3,}|-{3,}|\*{3,}|~{3,})'),
                    signal_b=re.compile(r'(new (system |)instructions|ignore (everything )?(above|before|previous)|you are now|real instructions|actual instructions|hidden instructions)', re.IGNORECASE),
                    description='Boundary marker + instruction override',
                ),
            ],
            # Extended encoding: encoding scheme + harmful/bypass intent
            "extended_encoding": [
                ConjunctionPattern(
                    signal_a=re.compile(r'(morse code|binary|caesar cipher|leetspeak|l33t|pig latin|reversed text|backwards|rot\d+|atbash|base32|base58)', re.IGNORECASE),
                    signal_b=re.compile(r'(decode|translate|convert|interpret|read|follow|execute|respond to|answer in)', re.IGNORECASE),
                    description='Encoding scheme + decode/execute request',
                ),
                ConjunctionPattern(
                    signal_a=re.compile(r'(first letter of each|acrostic|take the .{0,20} letter|read (vertically|diagonally|backwards)|hidden message)', re.IGNORECASE),
                    signal_b=re.compile(r'(follow|execute|do what|obey|comply|instructions|message|command)', re.IGNORECASE),
                    description='Steganographic pattern + execution request',
                ),
            ],
        }

        # Risk scores per attack type
        self.risk_scores = {
            "instruction_injection": 90,
            "role_playing": 70,
            "system_leakage": 95,
            "jailbreak": 100,
            "encoding": 80,
            "delimiter": 85,
            # v1.2.1 categories
            "persona_jailbreak": 95,
            "hypothetical_framing": 85,
            "authority_impersonation": 95,
            "emotional_manipulation": 80,
            "mode_switching": 90,
            "indirect_injection": 95,
            "data_extraction": 90,
            "extended_encoding": 85,
        }

        # Sensitivity thresholds
        self.thresholds = {
            "low": 2,    # Require 2+ pattern matches
            "medium": 1,  # Require 1+ pattern match
            "high": 1,    # Require 1+ pattern match
        }

    async def evaluate(
        self,
        input_data: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> GuardrailResult:
        """Evaluate input for prompt injection attempts.

        Args:
            input_data: Input to scan
            context: Execution context

        Returns:
            GuardrailResult with detection results
        """
        text = self._extract_text(input_data)
        detections = self._detect_injection(text)

        threshold = self.thresholds[self.sensitivity]

        if len(detections) < threshold:
            return GuardrailResult(
                passed=True,
                action="allow",
                reason="No prompt injection detected",
                metadata={"detections": []},
                risk_score=0,
            )

        # Calculate maximum risk score
        max_risk_score = max(self.risk_scores.get(d["type"], 50) for d in detections)

        # Determine action
        action = self.action
        passed = action in ["allow", "transform"]

        metadata: Dict[str, Any] = {"detections": detections}
        if action == "transform":
            metadata["transformed_text"] = self._transform_injection(text, detections)

        return GuardrailResult(
            passed=passed,
            action=action,
            reason=f"Detected {len(detections)} prompt injection pattern(s): {', '.join(d['type'] for d in detections)}",
            metadata=metadata,
            risk_score=max_risk_score,
        )

    def _extract_text(self, input_data: Any) -> str:
        """Extract text from various input formats."""
        if isinstance(input_data, str):
            return input_data

        if isinstance(input_data, dict):
            if "prompt" in input_data:
                return input_data["prompt"]
            if "messages" in input_data and isinstance(input_data["messages"], list):
                return " ".join(m.get("content", "") for m in input_data["messages"])
            if "text" in input_data:
                return input_data["text"]

        return str(input_data)

    def _detect_injection(self, text: str) -> List[Dict[str, Any]]:
        """Detect prompt injection patterns using both simple and conjunction matching."""
        detections: List[Dict[str, Any]] = []

        # Check simple regex patterns (single signal)
        for attack_type, patterns in self.patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    detections.append({
                        "type": attack_type,
                        "pattern": pattern.pattern,
                        "match": match.group(0),
                        "confidence": self._calculate_confidence(attack_type, match.group(0)),
                    })

        # Check conjunction patterns (require both signals to co-occur)
        for attack_type, conjunctions in self.conjunction_patterns.items():
            for conjunction in conjunctions:
                result = conjunction.match(text)
                if result:
                    match_a, match_b = result
                    detections.append({
                        "type": attack_type,
                        "pattern": conjunction.description,
                        "match": f"{match_a} ... {match_b}",
                        "confidence": self._calculate_confidence(attack_type, f"{match_a} {match_b}"),
                    })

        return detections

    def _calculate_confidence(self, attack_type: str, match: str) -> float:
        """Calculate confidence score for detection."""
        base_confidence = {
            "instruction_injection": 0.85,
            "role_playing": 0.70,
            "system_leakage": 0.95,
            "jailbreak": 0.98,
            "encoding": 0.75,
            "delimiter": 0.80,
            # v1.2.1 conjunction patterns have higher confidence
            # because they require 2 signals to co-occur
            "persona_jailbreak": 0.92,
            "hypothetical_framing": 0.88,
            "authority_impersonation": 0.93,
            "emotional_manipulation": 0.85,
            "mode_switching": 0.90,
            "indirect_injection": 0.93,
            "data_extraction": 0.90,
            "extended_encoding": 0.87,
        }

        return base_confidence.get(attack_type, 0.70)

    def _transform_injection(self, text: str, detections: List[Dict[str, Any]]) -> str:
        """Transform injection attempt to safer alternative."""
        # Sort by match length (longest first)
        sorted_detections = sorted(detections, key=lambda d: len(d["match"]), reverse=True)

        transformed = text
        for detection in sorted_detections:
            transformed = transformed.replace(detection["match"], "[FILTERED_INJECTION]")

        return transformed
