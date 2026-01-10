import jax.numpy as jnp
import numpy as np

# Star graph: node 0 is center, 1-4 are leaves
adj = np.zeros((5, 5))
for i in range(1, 5):
    adj[0, i] = 1
    adj[i, 0] = 1

print("Adjacency matrix:")
print(adj)

# Eigenvector centrality
eigenvalues, eigenvectors = jnp.linalg.eigh(jnp.array(adj))
print("\nEigenvalues:")
print(eigenvalues)

centrality = eigenvectors[:, -1]
print("\nCentrality (last eigenvector):")
print(centrality)

centrality_first = eigenvectors[:, 0]
print("\nCentrality (first eigenvector):")
print(centrality_first)
