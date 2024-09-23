import copy
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import torch
import torch_geometric
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from torch_geometric.data import Data
from mpl_toolkits.mplot3d import Axes3D


class Graph:
    def __init__(self, nodes, edge_dict, labels):
        """
        Initialize the Graph object.
        
        Args:
            nodes (torch.Tensor): Tensor representing node features.
            edge_dict (dict): Dictionary representing edges, where keys are node indices, and values are lists of neighbors.
            labels (dict): Dictionary where keys are node indices, and values are node labels.
        """
        self.nodes = nodes
        self.edge_dict = edge_dict
        self.labels = labels

    def add_daughter_cells(self, daughters, parent_index, daughter_labels):
        """
        Add daughter cells in place of the parent cell and update labels and edges.

        Args:
            daughters (torch.Tensor): Tensor representing the embeddings of the daughter nodes.
            parent_index (int): Index of the parent node to be replaced.
            daughter_labels (list): List containing labels for the daughter nodes.

        Returns:
            Graph: Updated graph with daughter nodes.
            torch.Tensor: Updated node embeddings.
        """
        keys = list(self.labels.keys())
        parent_pos = keys.index(parent_index)

        # Backup the part of the labels before the parent
        new_labels = {k: self.labels[k] for k in keys[:parent_pos]}

        # Assign the daughter labels at the correct positions
        new_labels[parent_index] = daughter_labels[0]  # First daughter
        new_labels[self.nodes.size(0)] = daughter_labels[1]  # Second daughter

        # Append the remaining labels after the parent
        new_labels.update({k: self.labels[k] for k in keys[parent_pos + 1:]})

        # Update labels
        self.labels = new_labels

        # Update the edge dictionary
        self.update_edge_dict(parent_index, daughter_labels[0], daughter_labels[1])

        return self.add_remove_nodes(daughters, parent_pos)

    def add_remove_nodes(self, new_nodes, parent_index):
        """
        Remove the parent node and add new daughter nodes.

        Args:
            new_nodes (torch.Tensor): Embeddings of the new nodes (daughters).
            parent_index (int): Index of the parent node to be removed.

        Returns:
            Graph: Updated graph with daughter nodes.
            torch.Tensor: Updated node embeddings.
        """
        if new_nodes.dim() == 1:
            new_nodes = new_nodes.unsqueeze(0)

        # Split the array at the parent index into two arrays
        left_nodes = self.nodes[:parent_index]
        right_nodes = self.nodes[parent_index + 1:]  # remove the parent node

        self.nodes = torch.cat([left_nodes, new_nodes, right_nodes])

        return Graph(self.nodes, self.edge_dict, self.labels), self.nodes

    def update_edge_dict(self, parent_index, daughter1, daughter2):
        """
        Update the edge_dict of the graph after adding daughter cells and removing a parent cell.
        
        Args:
            parent_index (int): Index of the parent node.
            daughter1 (str): Label of the first daughter node.
            daughter2 (str): Label of the second daughter node.
        """
        parent_neighbors = self.edge_dict.get(parent_index, [])

        if parent_index in self.edge_dict:
            del self.edge_dict[parent_index]

        daughter1_index = list(self.labels.keys())[list(self.labels.values()).index(daughter1)]
        daughter2_index = list(self.labels.keys())[list(self.labels.values()).index(daughter2)]

        self.edge_dict[daughter1_index] = [daughter2_index] + parent_neighbors
        self.edge_dict[daughter2_index] = [daughter1_index] + parent_neighbors

        for node, connections in self.edge_dict.items():
            if parent_index in connections:
                connections.remove(parent_index)
                if node not in [daughter1_index, daughter2_index]:
                    connections.extend([daughter1_index, daughter2_index])

    def to_data(self):
        """
        Convert the graph to a PyTorch Geometric Data object with edge weights.

        Returns:
            Data: PyTorch Geometric Data object.
        """
        edges = []
        edge_weights = []

        for node, destinations in self.edge_dict.items():
            for d in destinations:
                edges.append([node, d])
                pos1 = self.get_node_position_from_embeddings(node)
                pos2 = self.get_node_position_from_embeddings(d)
                weight = self.euclidean_distance_3d(pos1, pos2)
                edge_weights.append(weight)

        edges = torch.tensor(edges, dtype=torch.long).t().contiguous().to(self.nodes.device)
        edge_weights = torch.tensor(edge_weights, dtype=torch.float).to(self.nodes.device)

        return Data(
            x=self.nodes,
            edge_index=edges,
            edge_attr=edge_weights,
        )

    def get_node_position_from_embeddings(self, node_index):
        """
        Helper method to extract the position of a node from its embeddings.

        Args:
            node_index (int): Index of the node.

        Returns:
            torch.Tensor: 3D position of the node.
        """
        return self.nodes[node_index][:3]

    def euclidean_distance_3d(self, pos1, pos2):
        """
        Calculate Euclidean distance between two nodes in 3D space.

        Args:
            pos1 (torch.Tensor): Position of the first node (x, y, z).
            pos2 (torch.Tensor): Position of the second node (x, y, z).

        Returns:
            torch.Tensor: Euclidean distance between the nodes.
        """
        return torch.sqrt(torch.sum((pos1 - pos2) ** 2))

    def plot(self, fig=None, node_colors=None):
        """
        Plot the graph in 3D using NetworkX and Matplotlib.

        Args:
            fig (matplotlib.figure.Figure, optional): Figure object to plot the graph. Defaults to None.
            node_colors (list or str, optional): Colors for nodes. Defaults to None.

        Returns:
            np.ndarray: Image of the graph plot.
        """
        data = self.to_data()
        G = torch_geometric.utils.to_networkx(data, to_undirected=True)
        
        pos_3d = {i: self.get_node_position_from_embeddings(i).detach().cpu().numpy() for i in range(self.nodes.size(0))}

        if fig is None:
            fig = plt.figure()

        fig.clf()

        ax = fig.add_subplot(111, projection='3d')
        canvas = fig.canvas

        if node_colors is None:
            node_colors = 'blue'

        xs = [pos_3d[i][0] for i in range(self.nodes.size(0))]
        ys = [pos_3d[i][1] for i in range(self.nodes.size(0))]
        zs = [pos_3d[i][2] for i in range(self.nodes.size(0))]
        ax.scatter(xs, ys, zs, c=node_colors, s=100, depthshade=True)

        edgelist = [(key, value) for key, values in self.edge_dict.items() for value in values]
        for edge in edgelist:
            node1, node2 = edge
            x_vals = [pos_3d[node1][0], pos_3d[node2][0]]
            y_vals = [pos_3d[node1][1], pos_3d[node2][1]]
            z_vals = [pos_3d[node1][2], pos_3d[node2][2]]
            ax.plot(x_vals, y_vals, z_vals, color='black')

        for node, (x, y, z) in pos_3d.items():
            ax.text(x, y, z, f'{self.labels[node]}', color='red', fontsize=10)

        ax.set_xlabel('X axis')
        ax.set_ylabel('Y axis')
        ax.set_zlabel('Z axis')

        canvas.draw()

        image = np.frombuffer(canvas.tostring_rgb(), dtype="uint8")
        image = image.reshape(fig.canvas.get_width_height()[::-1] + (3,))

        return image

    def copy(self):
        """
        Create a deep copy of the graph.

        Returns:
            Graph: A new graph instance with copied data.
        """
        nodes = self.nodes * torch.ones(self.nodes.size(), device=self.nodes.device)
        edge_dict = copy.deepcopy(self.edge_dict)
        labels = copy.deepcopy(self.labels)
        return Graph(nodes, edge_dict, labels)
