#!/usr/bin/env python3
"""
Multi-user Eco client for GPBM workflow.

Supports separate user IDs for different agent roles and domains,
with comprehensive cross-user search capabilities.

Usage:
    # As library
    from gpbm.eco_client import EcoClient
    client = EcoClient()
    results = client.search_comprehensive("PID tuning", role="coder", domain="firmware")

    # As CLI
    python eco_client.py search "PID tuning" --role coder --domain firmware
    python eco_client.py post "Learned that..." --role coder --domain firmware
"""

import json
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import hashlib


@dataclass
class EcoConfig:
    """Configuration for Eco semantic memory server."""

    base_url: str = "https://eco.bennetleff.workers.dev"
    timeout: int = 10

    # Legacy user ID (where existing data lives per AGENTS.md)
    # This is always searched to ensure we find historical memories
    LEGACY: str = "temper-agent"

    # Shared user ID (read by all agents)
    SHARED: str = "temper-shared"

    # Role-specific user IDs
    ROLES: Dict[str, str] = field(
        default_factory=lambda: {
            "architect": "temper-architect",
            "coder": "temper-coder",
            "tester": "temper-tester",
            "human": "temper-human",
        }
    )

    # Domain-specific user IDs
    DOMAINS: Dict[str, str] = field(
        default_factory=lambda: {
            "firmware": "temper-firmware",
            "placer": "temper-placer",
            "pcb": "temper-pcb",
        }
    )

    def get_user_id(
        self, role: Optional[str] = None, domain: Optional[str] = None
    ) -> str:
        """Get the appropriate user ID for a role/domain combination."""
        if role and role in self.ROLES:
            return self.ROLES[role]
        if domain and domain in self.DOMAINS:
            return self.DOMAINS[domain]
        return self.SHARED


class EcoClient:
    """Client for Eco semantic memory with multi-user support."""

    def __init__(self, config: Optional[EcoConfig] = None):
        self.config = config or EcoConfig()

    def _make_request(
        self, endpoint: str, method: str = "GET", data: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Make HTTP request to Eco server."""
        url = f"{self.config.base_url}{endpoint}"

        try:
            if data:
                encoded = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=encoded,
                    headers={"Content-Type": "application/json"},
                    method=method,
                )
            else:
                req = urllib.request.Request(url, method=method)

            with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                if response.status in [200, 201]:
                    return json.load(response)
                return None
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            print(f"URL Error: {e.reason}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def search(
        self, query: str, user_id: str, limit: int = 5, min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search memories for a single user ID.

        Args:
            query: Search query string
            user_id: Eco user ID to search
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            List of memory results with scores
        """
        payload = {
            "query": query,
            "userId": user_id,
            "limit": limit,
            "minScore": min_score,
        }

        result = self._make_request("/memories/search", method="POST", data=payload)
        if result:
            return result.get("results", [])
        return []

    def search_comprehensive(
        self,
        query: str,
        role: Optional[str] = None,
        domain: Optional[str] = None,
        include_shared: bool = True,
        include_legacy: bool = True,
        limit: int = 10,
        min_score: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Search across multiple relevant user IDs.

        Searches shared + role-specific + domain-specific + legacy user IDs,
        deduplicates results, and returns sorted by score.

        Args:
            query: Search query string
            role: Agent role (architect, coder, tester, human)
            domain: Project domain (firmware, placer, pcb)
            include_shared: Include temper-shared in search
            include_legacy: Include temper-agent (legacy namespace with existing data)
            limit: Maximum total results
            min_score: Minimum similarity score

        Returns:
            Deduplicated list of results sorted by score
        """
        user_ids = []

        # Always include legacy namespace first (where most data lives)
        if include_legacy:
            user_ids.append(self.config.LEGACY)

        if include_shared:
            user_ids.append(self.config.SHARED)

        if role and role in self.config.ROLES:
            user_ids.append(self.config.ROLES[role])

        if domain and domain in self.config.DOMAINS:
            user_ids.append(self.config.DOMAINS[domain])

        # If no specific user IDs, at least search legacy
        if not user_ids:
            user_ids = [self.config.LEGACY]

        # Collect results from all user IDs
        all_results = []
        for user_id in user_ids:
            results = self.search(query, user_id, limit=limit, min_score=min_score)
            for r in results:
                r["source_user_id"] = user_id
            all_results.extend(results)

        # Dedupe by content hash, keep highest score
        seen: Dict[str, Dict] = {}
        for r in all_results:
            # Get content hash from result or compute it
            memory = r.get("memory", {})
            content = memory.get("content", "")
            hash_key = (
                memory.get("contentHash") or hashlib.md5(content.encode()).hexdigest()
            )

            if hash_key not in seen or r.get("score", 0) > seen[hash_key].get(
                "score", 0
            ):
                seen[hash_key] = r

        # Sort by score and limit
        sorted_results = sorted(
            seen.values(), key=lambda x: x.get("score", 0), reverse=True
        )
        return sorted_results[:limit]

    def post(
        self,
        content: str,
        user_id: str,
        tags: Optional[List[str]] = None,
        primary_sector: str = "episodic",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Post a memory to a specific user ID.

        Args:
            content: Memory content text
            user_id: Eco user ID
            tags: Optional list of tags
            primary_sector: Memory sector (episodic, semantic, procedural)
            metadata: Optional metadata dict

        Returns:
            True if successful
        """
        payload = {
            "content": content,
            "userId": user_id,
            "tags": tags or [],
            "primary_sector": primary_sector,
            "metadata": metadata or {},
        }

        result = self._make_request("/memories", method="POST", data=payload)
        return result is not None

    def post_reflection(
        self,
        content: str,
        role: str,
        domain: Optional[str] = None,
        tags: Optional[List[str]] = None,
        also_shared: bool = False,
        task_id: Optional[str] = None,
    ) -> bool:
        """Post a reflection to the appropriate user ID(s).

        Convenience method for posting agent learnings/reflections
        with proper routing based on role and domain.

        Args:
            content: Reflection content
            role: Agent role (architect, coder, tester, human)
            domain: Project domain (firmware, placer, pcb)
            tags: Additional tags
            also_shared: Also post to temper-shared
            task_id: bd task ID to link

        Returns:
            True if successful
        """
        # Build tags
        all_tags = list(tags or [])
        all_tags.append(f"role:{role}")
        if domain:
            all_tags.append(f"domain:{domain}")
        if task_id:
            all_tags.append(f"task:{task_id}")

        # Build metadata
        metadata = {}
        if task_id:
            metadata["task_id"] = task_id
        if domain:
            metadata["domain"] = domain

        # Determine primary user ID
        if role not in self.config.ROLES:
            print(f"Warning: Unknown role '{role}', using temper-shared")
            user_id = self.config.SHARED
        else:
            user_id = self.config.ROLES[role]

        # Post to primary user ID
        success = self.post(content, user_id, all_tags, metadata=metadata)

        # Optionally also post to shared
        if also_shared and success and user_id != self.config.SHARED:
            shared_tags = all_tags + ["cross-posted"]
            self.post(content, self.config.SHARED, shared_tags, metadata=metadata)

        return success

    def get_context_for_task(
        self,
        task_id: str,
        goal: Optional[str] = None,
        role: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Get comprehensive context for a task.

        Searches Eco for relevant memories based on task ID and goal,
        organized by source.

        Args:
            task_id: bd task ID
            goal: Task goal/description for semantic search
            role: Agent role
            domain: Project domain
            limit: Max results per category

        Returns:
            Dict with categorized context
        """
        context = {
            "task_id": task_id,
            "shared": [],
            "role_specific": [],
            "domain_specific": [],
            "task_related": [],
        }

        # Search for task ID mentions
        task_results = self.search(task_id, self.config.SHARED, limit=5)
        context["task_related"] = task_results

        # Search by goal if provided
        if goal:
            # Shared knowledge
            shared = self.search(goal, self.config.SHARED, limit=limit)
            context["shared"] = shared

            # Role-specific
            if role and role in self.config.ROLES:
                role_results = self.search(goal, self.config.ROLES[role], limit=limit)
                context["role_specific"] = role_results

            # Domain-specific
            if domain and domain in self.config.DOMAINS:
                domain_results = self.search(
                    goal, self.config.DOMAINS[domain], limit=limit
                )
                context["domain_specific"] = domain_results

        return context


def format_results(results: List[Dict], verbose: bool = False) -> str:
    """Format search results for display."""
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        memory = r.get("memory", {})
        score = r.get("score", 0)
        source = r.get("source_user_id", "unknown")
        content = memory.get("content", "")
        tags = memory.get("tags", [])

        # Truncate content for display
        if len(content) > 200 and not verbose:
            content = content[:200] + "..."

        lines.append(f"{i}. [{source}] (score: {score:.2f})")
        lines.append(f"   {content}")
        if tags:
            lines.append(f"   tags: {', '.join(tags)}")
        lines.append("")

    return "\n".join(lines)


def main():
    """CLI interface for Eco client."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Eco semantic memory client for GPBM workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search across all relevant user IDs
  python eco_client.py search "PID tuning algorithm" --role coder --domain firmware
  
  # Post a reflection
  python eco_client.py post "Learned that PID gains need..." --role coder --domain firmware
  
  # Post to shared knowledge
  python eco_client.py post "Project uses JAX for optimization" --role architect --shared
  
  # Get context for a task
  python eco_client.py context temper-xxx --goal "Implement PID improvements"
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search command
    search_parser = subparsers.add_parser("search", help="Search memories")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--role",
        choices=["architect", "coder", "tester", "human"],
        help="Agent role to search",
    )
    search_parser.add_argument(
        "--domain",
        choices=["firmware", "placer", "pcb"],
        help="Project domain to search",
    )
    search_parser.add_argument("--limit", type=int, default=10, help="Max results")
    search_parser.add_argument(
        "--min-score", type=float, default=0.7, help="Min similarity score"
    )
    search_parser.add_argument(
        "--no-shared", action="store_true", help="Exclude shared memories"
    )
    search_parser.add_argument(
        "--no-legacy", action="store_true", help="Exclude legacy temper-agent namespace"
    )
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")
    search_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show full content"
    )

    # Post command
    post_parser = subparsers.add_parser("post", help="Post a reflection")
    post_parser.add_argument("content", help="Memory content")
    post_parser.add_argument(
        "--role",
        required=True,
        choices=["architect", "coder", "tester", "human"],
        help="Agent role",
    )
    post_parser.add_argument(
        "--domain", choices=["firmware", "placer", "pcb"], help="Project domain"
    )
    post_parser.add_argument(
        "--shared", action="store_true", help="Also post to temper-shared"
    )
    post_parser.add_argument("--task", help="Link to bd task ID")
    post_parser.add_argument("--tags", nargs="*", default=[], help="Additional tags")

    # Context command
    context_parser = subparsers.add_parser("context", help="Get context for a task")
    context_parser.add_argument("task_id", help="bd task ID")
    context_parser.add_argument("--goal", help="Task goal for semantic search")
    context_parser.add_argument(
        "--role", choices=["architect", "coder", "tester", "human"], help="Agent role"
    )
    context_parser.add_argument(
        "--domain", choices=["firmware", "placer", "pcb"], help="Project domain"
    )
    context_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # User IDs command (informational)
    ids_parser = subparsers.add_parser("ids", help="List available user IDs")

    args = parser.parse_args()
    client = EcoClient()

    if args.command == "search":
        results = client.search_comprehensive(
            args.query,
            role=args.role,
            domain=args.domain,
            include_shared=not args.no_shared,
            include_legacy=not args.no_legacy,
            limit=args.limit,
            min_score=args.min_score,
        )

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(format_results(results, verbose=args.verbose))

    elif args.command == "post":
        success = client.post_reflection(
            args.content,
            role=args.role,
            domain=args.domain,
            tags=args.tags,
            also_shared=args.shared,
            task_id=args.task,
        )

        if success:
            print(f"✓ Posted to {client.config.ROLES.get(args.role, 'unknown')}")
            if args.shared:
                print(f"✓ Also posted to {client.config.SHARED}")
        else:
            print("✗ Failed to post")
            exit(1)

    elif args.command == "context":
        context = client.get_context_for_task(
            args.task_id, goal=args.goal, role=args.role, domain=args.domain
        )

        if args.json:
            print(json.dumps(context, indent=2))
        else:
            print(f"=== Context for {args.task_id} ===\n")

            if context["task_related"]:
                print("Task-related memories:")
                print(format_results(context["task_related"]))

            if context["shared"]:
                print("Shared knowledge:")
                print(format_results(context["shared"]))

            if context["role_specific"]:
                print(f"Role-specific ({args.role}):")
                print(format_results(context["role_specific"]))

            if context["domain_specific"]:
                print(f"Domain-specific ({args.domain}):")
                print(format_results(context["domain_specific"]))

    elif args.command == "ids":
        print("Available Eco User IDs:\n")
        print(f"Legacy:   {client.config.LEGACY}  (where existing data lives)")
        print(f"Shared:   {client.config.SHARED}")
        print("\nRoles:")
        for role, uid in client.config.ROLES.items():
            print(f"  {role:12} → {uid}")
        print("\nDomains:")
        for domain, uid in client.config.DOMAINS.items():
            print(f"  {domain:12} → {uid}")


if __name__ == "__main__":
    main()
