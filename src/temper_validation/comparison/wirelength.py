__all__ = ["manhattan_wirelength", "steiner_wirelength", "compare_wirelength"]


def manhattan_wirelength(placement, net):
    pins = [placement[pin] for pin in net]
    total = 0
    for i in range(len(pins)):
        for j in range(i + 1, len(pins)):
            dx = abs(pins[i][0] - pins[j][0])
            dy = abs(pins[i][1] - pins[j][1])
            total += dx + dy
    return total


def steiner_wirelength(placement, net):
    pins = [placement[pin] for pin in net]
    n = len(pins)
    if n <= 1:
        return 0
    # Build adjacency matrix with Manhattan distances
    distances = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dx = abs(pins[i][0] - pins[j][0])
            dy = abs(pins[i][1] - pins[j][1])
            dist = dx + dy
            distances[i][j] = dist
            distances[j][i] = dist
    # Prim's algorithm
    visited = [False] * n
    min_dist = [float("inf")] * n
    min_dist[0] = 0
    total = 0
    for _ in range(n):
        u = -1
        for i in range(n):
            if not visited[i] and (u == -1 or min_dist[i] < min_dist[u]):
                u = i
        visited[u] = True
        total += min_dist[u]
        for v in range(n):
            if not visited[v] and distances[u][v] < min_dist[v]:
                min_dist[v] = distances[u][v]
    return total


def compare_wirelength(optimized, reference):
    ratio = optimized / reference
    verdict = "PASS" if ratio < 1.1 else "FAIL"
    return {"ratio": ratio, "verdict": verdict}
