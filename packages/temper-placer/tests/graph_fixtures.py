"""Minimal networkx-compatible graph containers + algorithms for the test suite.

networkx was removed from the production tree during the wave-4 Rust migration
(no ``import networkx`` remains under ``packages/*/src``). It survived only as
a test dependency: ~40 test files used it as an input-builder (an
insertion-ordered stand-in for the Rust ``SkeletonGraph``/``PathGraph``
pyclasses) and as differential oracles. This module implements the exact
subset those tests touch, with networkx-3.6.1 semantics:

- containers: ``Graph`` (undirected), ``DiGraph``, ``MultiDiGraph`` —
  insertion-ordered nodes/edges, dict-of-dicts adjacency.
- algorithms: ``is_connected``, ``connected_components``,
  ``number_connected_components``, ``minimum_cut`` (Edmonds-Karp with
  bidirectional BFS, ported from networkx 3.6.1's ``edmonds_karp_core``),
  single-target ``shortest_path_length``.
- serialization: ``node_link_data``.

The load-bearing semantics are (a) node/edge **iteration order** — the
``*_rust_differential`` tests pin bit-exact output against these containers —
and (b) ``minimum_cut``'s node partition, which depends on the exact
augmenting-path selection of networkx's bidirectional-BFS Edmonds-Karp. Both
were verified parity-exact against networkx 3.6.1 by a throwaway harness
before networkx was removed from the environment (see
``docs/evidence/2026-08-15-networkx-test-dependency-removal.md``).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

__all__ = [
    "Graph",
    "DiGraph",
    "MultiDiGraph",
    "is_connected",
    "connected_components",
    "number_connected_components",
    "minimum_cut",
    "node_link_data",
    "algorithms",
]


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------


class NodeView:
    """Insertion-ordered view of ``G._node`` (attrs dicts) mirroring nx's."""

    __slots__ = ("_node",)

    def __init__(self, node: dict):
        self._node = node

    def __iter__(self) -> Iterator:
        return iter(self._node)

    def __len__(self) -> int:
        return len(self._node)

    def __contains__(self, n) -> bool:
        return n in self._node

    def __getitem__(self, n):
        return self._node[n]

    def __call__(self, data=False, default=None):
        if data is False:
            return self
        return _NodeDataView(self._node, data, default)

    def __repr__(self) -> str:
        return f"NodeView({list(self._node)!r})"


class _NodeDataView:
    """Minimal stand-in for ``NodeDataView`` (``G.nodes(data=True)``)."""

    __slots__ = ("_node", "_data", "_default")

    def __init__(self, node: dict, data, default):
        self._node = node
        self._data = data
        self._default = default

    def __iter__(self):
        if self._data is True:
            for n, attrs in self._node.items():
                yield n, dict(attrs)
        else:
            for n, attrs in self._node.items():
                yield n, attrs.get(self._data, self._default)

    def __len__(self) -> int:
        return len(self._node)

    def __contains__(self, n) -> bool:
        return n in self._node


class EdgeView:
    """Edge iteration mirroring nx's per-graph-type ordering.

    ``Graph.edges`` yields each undirected edge once (self-loops included) in
    the order networkx does: walk adjacency in node-insertion order, yield
    ``(u, v)`` the first time ``v`` is seen as a neighbor, and mark ``n`` as
    seen only *after* processing its whole neighbor list — so a self-loop on
    ``n`` passes the check and is yielded exactly once. ``DiGraph.edges``
    yields every directed edge in adjacency order with no dedup.
    ``MultiDiGraph.edges`` (the property, iterated directly) yields
    ``(u, v, key)`` triples; ``MultiDiGraph.edges(...)`` (a call) yields
    ``(u, v)`` or ``(u, v, data)`` unless ``keys=True``, mirroring
    ``OutMultiEdgeView`` vs ``OutMultiEdgeDataView``.
    """

    __slots__ = ("_G",)

    def __init__(self, G):
        self._G = G

    def __call__(self, nbunch=None, data=False, *, default=None, keys=False):
        return self._edge_iter(data, default, keys, nbunch)

    def data(self, data=True, default=None, nbunch=None, keys=False):
        return self._edge_iter(data, default, keys, nbunch)

    def __iter__(self):
        return self._edge_iter(False, None, self._G._multigraph, None)

    def __len__(self):
        return self._G.number_of_edges()

    def _nbunch_nodes(self, nbunch):
        """Normalize ``nbunch`` to a node-id set, or ``None`` meaning "no
        restriction" -- mirrors nx's ``Graph.nbunch_iter`` for the shapes
        this test suite passes: a bare node id (restricts to edges FROM that
        node) or an iterable of node ids. A single node not present in the
        graph, or an iterable containing none that are, yields no edges --
        nx never raises for that, it is simply empty. This is the piece a
        raw ``adj.items()`` walk (the pre-fix state) silently dropped: a
        caller passing ``nbunch`` got every edge in the graph back, not just
        the ones incident to the nodes it asked for.
        """
        if nbunch is None:
            return None
        nodes = self._G._node
        try:
            if nbunch in nodes:
                return {nbunch}
        except TypeError:
            pass  # unhashable (e.g. a list) -- fall through to iteration
        try:
            return {n for n in nbunch if n in nodes}
        except TypeError:
            return set()

    def _edge_iter(self, data, default, keys, nbunch=None):
        G = self._G
        adj = G._adj
        restrict = self._nbunch_nodes(nbunch)
        if G._multigraph:
            if keys:
                for u, vdict in adj.items():
                    if restrict is not None and u not in restrict:
                        continue
                    for v, keydict in vdict.items():
                        for k, attrs in keydict.items():
                            if data is False:
                                yield (u, v, k)
                            elif data is True:
                                yield (u, v, k, attrs)
                            else:
                                yield (u, v, k, attrs.get(data, default))
            else:
                for u, vdict in adj.items():
                    if restrict is not None and u not in restrict:
                        continue
                    for v, keydict in vdict.items():
                        for k, attrs in keydict.items():
                            if data is False:
                                yield (u, v)
                            elif data is True:
                                yield (u, v, attrs)
                            else:
                                yield (u, v, attrs.get(data, default))
        elif G._directed:
            for n, nbrs in adj.items():
                if restrict is not None and n not in restrict:
                    continue
                for nbr in nbrs:
                    if data is False:
                        yield (n, nbr)
                    elif data is True:
                        yield (n, nbr, adj[n][nbr])
                    else:
                        yield (n, nbr, adj[n][nbr].get(data, default))
        else:
            seen = {}
            for n, nbrs in adj.items():
                # A node excluded by `restrict` is never marked `seen`: it
                # is never visited as an outer node in real nx's restricted
                # iteration either, and marking it here would wrongly
                # suppress a later included node's edge back to it (e.g.
                # `edges(nbunch=only_the_second_endpoint)` would emit
                # nothing for that edge instead of one entry).
                if restrict is not None and n not in restrict:
                    continue
                for nbr in nbrs:
                    if nbr not in seen:
                        if data is False:
                            yield (n, nbr)
                        elif data is True:
                            yield (n, nbr, adj[n][nbr])
                        else:
                            yield (n, nbr, adj[n][nbr].get(data, default))
                seen[n] = 1


class Graph:
    """Undirected simple graph; insertion-ordered nodes and edges."""

    _directed = False
    _multigraph = False

    def __init__(self, incoming_graph_data=None, **attr):
        self._node = {}
        self._adj = {}
        self.graph = {}
        if incoming_graph_data is not None:
            if hasattr(incoming_graph_data, "nodes"):
                self.add_nodes_from(incoming_graph_data.nodes)
                self.add_edges_from(incoming_graph_data.edges(data=True))
            else:
                data = list(incoming_graph_data)
                if data and not _is_edge(data[0]):
                    self.add_nodes_from(data)
                else:
                    self.add_edges_from(data)
        self.graph.update(attr)

    @property
    def nodes(self) -> NodeView:
        return NodeView(self._node)

    @property
    def edges(self) -> EdgeView:
        return EdgeView(self)

    @property
    def adj(self):
        return self._adj

    def __getitem__(self, n):
        return self._adj[n]

    def __iter__(self):
        return iter(self._node)

    def __len__(self):
        return len(self._node)

    def __contains__(self, n):
        return n in self._node

    def is_directed(self) -> bool:
        return self._directed

    def is_multigraph(self) -> bool:
        return self._multigraph

    def number_of_nodes(self) -> int:
        return len(self._node)

    def number_of_edges(self) -> int:
        if self._multigraph:
            return sum(
                len(kd) for n, nbrs in self._adj.items() for nbr, kd in nbrs.items()
            )
        if self._directed:
            return sum(len(nbrs) for nbrs in self._adj.values())
        return sum(len(nbrs) + (n in nbrs) for n, nbrs in self._adj.items()) // 2

    def has_node(self, n) -> bool:
        return n in self._node

    def has_edge(self, u, v) -> bool:
        return u in self._adj and v in self._adj[u]

    def size(self, weight=None):
        """Real nx ``Graph.size``: edge count, or the summed ``weight``
        attribute across edges when given (each edge counted once).
        """
        if weight is None:
            return self.number_of_edges()
        return sum(attrs.get(weight, 1) for _u, _v, attrs in self.edges(data=True))

    def edges_with_data(self) -> list[tuple]:
        """``SkeletonGraph``-parity convenience: the Rust pyclass's
        ``edges_with_data()`` method, called by ``bundle_analyzer.py``'s
        ``_compute_median_edge_length`` (``skeleton.graph.edges_with_data()``,
        annotated ``# type: ignore[attr-defined]`` there since it is not on
        real nx's ``Graph``). Same shape as ``list(self.edges(data=True))``.
        """
        return list(self.edges(data=True))

    def connected_components(self) -> list[set]:
        """List (not generator) form of the module-level
        :func:`connected_components`, matching the Rust ``SkeletonGraph``
        pyclass this fixture also stands in for -- see this module's
        docstring ("an input-builder ... stand-in for the Rust
        SkeletonGraph/PathGraph pyclasses"). ``channel_skeleton.py``'s
        ``_ensure_skeleton_connectivity`` (the production caller this
        fixture is built to feed) calls ``G.connected_components()`` as a
        METHOD and immediately does ``len(components)`` /
        ``enumerate(components)`` on the result, which real networkx's
        free-function generator does not support directly. Real networkx
        itself has no such method on ``Graph`` -- this exists only for
        parity with the production Rust type, not as nx-compatibility.
        """
        return list(connected_components(self))

    def is_connected(self) -> bool:
        """Method form of the module-level :func:`is_connected`, for the
        same ``SkeletonGraph``-parity reason as :meth:`connected_components`
        above -- ``channel_skeleton.py``'s ``ChannelSkeleton.is_connected``
        property calls ``self.graph.is_connected()``.
        """
        return is_connected(self)

    def add_node(self, n, **attr):
        if n not in self._node:
            self._node[n] = {}
            self._adj[n] = {}
        self._node[n].update(attr)

    def add_nodes_from(self, nodes_for_adding, **attr):
        for n in nodes_for_adding:
            try:
                newnode = n not in self._node
                newdict = attr
            except TypeError:
                n, ndict = n
                newnode = n not in self._node
                newdict = attr.copy()
                newdict.update(ndict)
            if newnode:
                if n is None:
                    raise ValueError("None cannot be a node")
                self._adj[n] = {}
                self._node[n] = {}
            self._node[n].update(newdict)

    def add_edge(self, u, v, **attr):
        self._node.setdefault(u, {})
        self._adj.setdefault(u, {})
        self._node.setdefault(v, {})
        self._adj.setdefault(v, {})
        if v in self._adj[u]:
            self._adj[u][v].update(attr)
            if not self._directed:
                self._adj[v][u].update(attr)
        else:
            if self._directed:
                self._adj[u][v] = dict(attr)
            else:
                data = dict(attr)
                self._adj[u][v] = data
                self._adj[v][u] = data

    def add_edges_from(self, ebunch, **attr):
        for e in ebunch:
            ne = len(e)
            if ne == 3:
                u, v, dd = e
            elif ne == 2:
                u, v = e
                dd = {}
            else:
                raise ValueError(f"Edge tuple {e!r} must have 2 or 3 elements")
            d = dict(attr)
            d.update(dd)
            self.add_edge(u, v, **d)

    def remove_node(self, n):
        nbrs = list(self._adj[n])
        for nbr in nbrs:
            del self._adj[nbr][n]
        del self._adj[n]
        del self._node[n]

    def remove_edges_from(self, ebunch):
        for e in ebunch:
            u, v = e[0], e[1]
            if v in self._adj[u]:
                del self._adj[u][v]
                if not self._directed:
                    del self._adj[v][u]

    def neighbors(self, n):
        return iter(self._adj[n])

    def copy(self):
        G = self.__class__()
        G.graph.update(self.graph)
        G._node = {n: dict(a) for n, a in self._node.items()}
        G._adj = {u: {v: dict(a) for v, a in nbrs.items()} for u, nbrs in self._adj.items()}
        return G


class DiGraph(Graph):
    """Directed graph; ``_adj`` is the successor adjacency, ``_pred`` mirrors it."""

    _directed = True

    def __init__(self, incoming_graph_data=None, **attr):
        self.graph = {}
        self._node = {}
        self._adj = {}
        self._pred = {}
        if incoming_graph_data is not None:
            if hasattr(incoming_graph_data, "nodes"):
                self.add_nodes_from(incoming_graph_data.nodes)
                self.add_edges_from(incoming_graph_data.edges(data=True))
            else:
                data = list(incoming_graph_data)
                if data and not _is_edge(data[0]):
                    self.add_nodes_from(data)
                else:
                    self.add_edges_from(data)
        self.graph.update(attr)

    @property
    def pred(self):
        return self._pred

    @property
    def succ(self):
        return self._adj

    def add_node(self, n, **attr):
        super().add_node(n, **attr)
        self._pred.setdefault(n, {})

    def add_nodes_from(self, nodes_for_adding, **attr):
        for n in nodes_for_adding:
            try:
                newnode = n not in self._node
                newdict = attr
            except TypeError:
                n, ndict = n
                newnode = n not in self._node
                newdict = attr.copy()
                newdict.update(ndict)
            if newnode:
                if n is None:
                    raise ValueError("None cannot be a node")
                self._adj[n] = {}
                self._pred[n] = {}
                self._node[n] = {}
            self._node[n].update(newdict)

    def add_edge(self, u, v, **attr):
        self._node.setdefault(u, {})
        self._adj.setdefault(u, {})
        self._pred.setdefault(u, {})
        self._node.setdefault(v, {})
        self._adj.setdefault(v, {})
        self._pred.setdefault(v, {})
        if v in self._adj[u]:
            self._adj[u][v].update(attr)
            self._pred[v][u].update(attr)
        else:
            data = dict(attr)
            self._adj[u][v] = data
            self._pred[v][u] = data

    def add_edges_from(self, ebunch, **attr):
        for e in ebunch:
            ne = len(e)
            if ne == 3:
                u, v, dd = e
            elif ne == 2:
                u, v = e
                dd = {}
            else:
                raise ValueError(f"Edge tuple {e!r} must have 2 or 3 elements")
            d = dict(attr)
            d.update(dd)
            self.add_edge(u, v, **d)

    def remove_node(self, n):
        for p in list(self._pred[n]):
            del self._adj[p][n]
        for s in list(self._adj[n]):
            del self._pred[s][n]
        del self._pred[n]
        del self._adj[n]
        del self._node[n]

    def remove_edges_from(self, ebunch):
        for e in ebunch:
            u, v = e[0], e[1]
            if v in self._adj[u]:
                del self._adj[u][v]
                del self._pred[v][u]

    def copy(self):
        G = self.__class__()
        G.graph.update(self.graph)
        G._node = {n: dict(a) for n, a in self._node.items()}
        G._adj = {u: {v: dict(a) for v, a in nbrs.items()} for u, nbrs in self._adj.items()}
        G._pred = {u: {v: dict(a) for v, a in nbrs.items()} for u, nbrs in self._pred.items()}
        return G


class MultiDiGraph(DiGraph):
    """Directed multigraph; edges keyed 0, 1, 2, ... per (u, v) pair."""

    _directed = True
    _multigraph = True

    def __init__(self, incoming_graph_data=None, **attr):
        # Replicate DiGraph init but with multigraph adjacency shape.
        self._node = {}
        self._adj = {}
        self._pred = {}
        self.graph = {}
        if incoming_graph_data is not None:
            if hasattr(incoming_graph_data, "nodes"):
                self.add_nodes_from(incoming_graph_data.nodes)
                self.add_edges_from(incoming_graph_data.edges(keys=True, data=True))
            else:
                data = list(incoming_graph_data)
                if data and not _is_edge(data[0]):
                    self.add_nodes_from(data)
                else:
                    self.add_edges_from(data)
        self.graph.update(attr)

    def add_node(self, n, **attr):
        if n not in self._node:
            self._node[n] = {}
            self._adj[n] = {}
            self._pred[n] = {}
        self._node[n].update(attr)

    def new_edge_key(self, u, v):
        try:
            keydict = self._adj[u][v]
        except KeyError:
            return 0
        key = len(keydict)
        while key in keydict:
            key += 1
        return key

    def add_edge(self, u, v, key=None, **attr):
        if u not in self._adj:
            self._adj[u] = {}
            self._pred[u] = {}
            self._node[u] = {}
        if v not in self._adj:
            self._adj[v] = {}
            self._pred[v] = {}
            self._node[v] = {}
        if key is None:
            key = self.new_edge_key(u, v)
        if v in self._adj[u]:
            keydict = self._adj[u][v]
            datadict = keydict.get(key, {})
            datadict.update(attr)
            keydict[key] = datadict
        else:
            datadict = dict(attr)
            keydict = {key: datadict}
            self._adj[u][v] = keydict
            self._pred[v][u] = keydict
        return key

    def add_edges_from(self, ebunch_to_add, **attr):
        keylist = []
        for e in ebunch_to_add:
            ne = len(e)
            if ne == 4:
                u, v, key, dd = e
            elif ne == 3:
                u, v, dd = e
                key = None
            elif ne == 2:
                u, v = e
                dd = {}
                key = None
            else:
                raise ValueError(
                    f"Edge tuple {e} must be a 2-tuple, 3-tuple or 4-tuple."
                )
            ddd = {}
            ddd.update(attr)
            try:
                ddd.update(dd)
            except (TypeError, ValueError):
                if ne != 3:
                    raise
                key = dd
            key = self.add_edge(u, v, key)
            self._adj[u][v][key].update(ddd)
            keylist.append(key)
        return keylist

    def remove_edges_from(self, ebunch):
        for e in ebunch:
            try:
                u, v, k = e[:3]
            except (ValueError, TypeError):
                u, v = e
                k = None
            if u in self._adj and v in self._adj[u]:
                if k is None or k in self._adj[u][v]:
                    if k is None:
                        del self._adj[u][v]
                        del self._pred[v][u]
                    else:
                        del self._adj[u][v][k]
                        if not self._adj[u][v]:
                            del self._adj[u][v]
                            del self._pred[v][u]

    def copy(self):
        G = self.__class__()
        G.graph.update(self.graph)
        G._node = {n: dict(a) for n, a in self._node.items()}
        G._adj = {
            u: {v: {k: dict(a) for k, a in keydict.items()} for v, keydict in vdict.items()}
            for u, vdict in self._adj.items()
        }
        G._pred = {
            u: {v: {k: dict(a) for k, a in keydict.items()} for v, keydict in vdict.items()}
            for u, vdict in self._pred.items()
        }
        return G


def _is_edge(item) -> bool:
    return isinstance(item, tuple) and len(item) in (2, 3, 4)


# ---------------------------------------------------------------------------
# Algorithms
# ---------------------------------------------------------------------------


def _plain_bfs(G, source):
    """Yield nodes of the connected component of ``source`` in BFS order."""
    seen = {source}
    nextlevel = [source]
    while nextlevel:
        thislevel = nextlevel
        nextlevel = []
        for v in thislevel:
            yield v
            for w in G[v]:
                if w not in seen:
                    seen.add(w)
                    nextlevel.append(w)


def connected_components(G):
    seen = set()
    for v in G:
        if v not in seen:
            c = set(_plain_bfs(G, v))
            yield c
            seen.update(c)


def number_connected_components(G) -> int:
    return sum(1 for _ in connected_components(G))


def is_connected(G) -> bool:
    if len(G) == 0:
        raise ValueError("is_connected is not defined for the empty graph")
    if len(G) == 1:
        return True
    return len(next(iter(connected_components(G)))) == len(G)


def single_target_shortest_path_length(G, target, cutoff=None):
    """Distances from every node that can reach ``target`` (reverse BFS)."""
    lengths = {target: 0}
    nextlevel = [target]
    while nextlevel:
        thislevel = nextlevel
        nextlevel = []
        for v in thislevel:
            for w in G.pred[v]:
                if w not in lengths:
                    lengths[w] = lengths[v] + 1
                    if cutoff is None or lengths[w] <= cutoff:
                        nextlevel.append(w)
    return lengths


# -- minimum_cut: Edmonds-Karp, ported from networkx 3.6.1 ------------------


def _build_residual_network(G, capacity):
    if G.is_multigraph():
        raise ValueError("MultiGraph and MultiDiGraph not supported (yet).")
    R = DiGraph()
    R.add_nodes_from(G)
    inf = float("inf")
    edge_list = [
        (u, v, attr)
        for u, v, attr in G.edges(data=True)
        if u != v and attr.get(capacity, inf) > 0
    ]
    inf = (
        3
        * sum(
            attr[capacity]
            for u, v, attr in edge_list
            if capacity in attr and attr[capacity] != inf
        )
        or 1
    )
    if G.is_directed():
        for u, v, attr in edge_list:
            r = min(attr.get(capacity, inf), inf)
            if not R.has_edge(u, v):
                R.add_edge(u, v, capacity=r)
                R.add_edge(v, u, capacity=0)
            else:
                R._adj[u][v]["capacity"] = r
    else:
        for u, v, attr in edge_list:
            r = min(attr.get(capacity, inf), inf)
            R.add_edge(u, v, capacity=r)
            R.add_edge(v, u, capacity=r)
    R.graph["inf"] = inf
    return R


def _edmonds_karp_core(R, s, t, cutoff):
    R_succ = R.succ
    R_pred = R.pred
    inf = R.graph["inf"]

    def augment(path):
        flow = inf
        it = iter(path)
        u = next(it)
        for v in it:
            attr = R_succ[u][v]
            flow = min(flow, attr["capacity"] - attr["flow"])
            u = v
        if flow * 2 > inf:
            raise OverflowError("Infinite capacity path, flow unbounded above.")
        it = iter(path)
        u = next(it)
        for v in it:
            R_succ[u][v]["flow"] += flow
            R_succ[v][u]["flow"] -= flow
            u = v
        return flow

    def bidirectional_bfs():
        pred = {s: None}
        q_s = [s]
        succ = {t: None}
        q_t = [t]
        while True:
            q = []
            if len(q_s) <= len(q_t):
                for u in q_s:
                    for v, attr in R_succ[u].items():
                        if v not in pred and attr["flow"] < attr["capacity"]:
                            pred[v] = u
                            if v in succ:
                                return v, pred, succ
                            q.append(v)
                if not q:
                    return None, None, None
                q_s = q
            else:
                for u in q_t:
                    for v, attr in R_pred[u].items():
                        if v not in succ and attr["flow"] < attr["capacity"]:
                            succ[v] = u
                            if v in pred:
                                return v, pred, succ
                            q.append(v)
                if not q:
                    return None, None, None
                q_t = q

    flow_value = 0
    while flow_value < cutoff:
        v, pred, succ = bidirectional_bfs()
        if pred is None:
            break
        path = [v]
        u = v
        while u != s:
            u = pred[u]
            path.append(u)
        path.reverse()
        u = v
        while u != t:
            u = succ[u]
            path.append(u)
        flow_value += augment(path)
    return flow_value


def _edmonds_karp_impl(G, s, t, capacity, cutoff):
    if s not in G:
        raise KeyError(f"node {s} not in graph")
    if t not in G:
        raise KeyError(f"node {t} not in graph")
    if s == t:
        raise ValueError("source and sink are the same node")
    R = _build_residual_network(G, capacity)
    for u in R:
        for e in R[u].values():
            e["flow"] = 0
    if cutoff is None:
        cutoff = float("inf")
    R.graph["flow_value"] = _edmonds_karp_core(R, s, t, cutoff)
    return R


def minimum_cut(G, s, t, capacity="capacity", flow_func=None):
    """Minimum (s, t)-cut value and node partition (Edmonds-Karp semantics).

    Mirrors networkx's ``minimum_cut``: compute the max flow, remove
    saturated residual edges, then the partition is
    ``(nodes - reachable_to_t, reachable_to_t)`` where reachability is in
    the residual network. ``flow_func`` is accepted for API compatibility
    and ignored — this implementation always uses the bidirectional-BFS
    Edmonds-Karp that networkx 3.6.1's ``edmonds_karp_core`` performs (the
    only flow_func the tests ever passed).
    """
    if flow_func is not None and not callable(flow_func):
        raise TypeError("flow_func has to be callable.")
    R = _edmonds_karp_impl(G, s, t, capacity, None)
    cutset = [(u, v, d) for u, v, d in R.edges(data=True) if d["flow"] == d["capacity"]]
    R.remove_edges_from(cutset)
    non_reachable = set(single_target_shortest_path_length(R, t))
    partition = (set(G) - non_reachable, non_reachable)
    return (R.graph["flow_value"], partition)


# -- serialization -----------------------------------------------------------


def node_link_data(G, *, source="source", target="target", name="id", key="key",
                   edges="edges", nodes="nodes"):
    """Return node-link formatted data, mirroring ``networkx.readwrite``."""
    multigraph = G.is_multigraph()
    key = None if not multigraph else key
    if len({source, target, key}) < 3:
        raise ValueError("Attribute names are not unique.")
    data = {
        "directed": G.is_directed(),
        "multigraph": multigraph,
        "graph": G.graph,
        nodes: [{**G.nodes[n], name: n} for n in G],
    }
    if multigraph:
        data[edges] = [
            {**d, source: u, target: v, key: k}
            for u, v, k, d in G.edges(keys=True, data=True)
        ]
    else:
        data[edges] = [{**d, source: u, target: v} for u, v, d in G.edges(data=True)]
    return data


# ---------------------------------------------------------------------------
# networkx namespace compatibility
# ---------------------------------------------------------------------------


class _EdmondsKarpCompat:
    """API-compat stand-in for ``nx.algorithms.flow.edmonds_karp``."""

    def __call__(self, *args, **kwargs):
        raise NotImplementedError(
            "graph_fixtures implements minimum_cut directly; edmonds_karp is "
            "accepted as a flow_func marker but never invoked."
        )


class _FlowCompat:
    edmonds_karp = _EdmondsKarpCompat()


class _AlgorithmsCompat:
    flow = _FlowCompat()


algorithms = _AlgorithmsCompat()
