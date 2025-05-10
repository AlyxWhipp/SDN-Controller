#Alyx Whipp
#CSC 4501
#SDN controller


import networkx as nx
import matplotlib.pyplot as plt
from operator import itemgetter
from cmd import Cmd
import hashlib


class SDNController:
    def __init__(self):
        self.topology = nx.Graph()
        self.flow_tables = {}  # {switch: {destination: path}}
        self.traffic = {}  # {(src,dst): {'type': str, 'priority': int}}
        self.link_utilization = {}  # {(u,v): utilization}
        self.backup_paths = {}  # {(src,dst): [backup_paths]}
        self.priority_map = {'critical': 3, 'important': 2, 'default': 1}

    def add_node(self, *nodes):
        for node in nodes:
            self.topology.add_node(node)
            self.flow_tables[node] = {}
            print(f"added nodes: {node}")

    def add_link(self, u, v, weight, capacity):
        self.topology.add_edge(u, v, weight=weight, capacity=capacity)
        self.link_utilization[(u, v)] = 0
        self.link_utilization[(v, u)] = 0

    def remove_link(self, u, v):
        if self.topology.has_edge(u, v):
            self.topology.remove_edge(u, v)
            self.link_utilization.pop((u, v), None)
            self.link_utilization.pop((v, u), None)
            self._handle_link_failure(u, v)

    def compute_paths(self):
        for src in self.topology.nodes:
            for dst in self.topology.nodes:
                if src != dst:
                    self._compute_path_with_priority(src, dst)

    def _compute_path_with_priority(self, src, dst):
        try:
            # Get all possible paths sorted by priority
            all_paths = list(nx.all_simple_paths(self.topology, src, dst))

            if not all_paths:
                self.flow_tables[src][dst] = None
                return

            # Prioritize paths based on traffic type and current utilization
            traffic_info = self.traffic.get((src, dst), {'type': 'default', 'priority': 1})
            priority = traffic_info['priority']

            if priority == self.priority_map['critical']:
                # For critical traffic, use shortest path
                path = nx.shortest_path(self.topology, src, dst, weight='weight')
            else:
                # For other traffic, consider load balancing
                path = self._select_load_balanced_path(all_paths)

            self.flow_tables[src][dst] = path

            # Store backup paths (all alternative paths)
            if len(all_paths) > 1:
                self.backup_paths[(src, dst)] = [p for p in all_paths if p != path]

        except nx.NetworkXNoPath:
            self.flow_tables[src][dst] = None

    def _select_load_balanced_path(self, paths):
        path_utils = []
        for path in paths:
            utilization = sum(self.link_utilization.get((path[i], path[i + 1]), 0)
                              for i in range(len(path) - 1))
            path_utils.append((utilization, path))


        return min(path_utils, key=itemgetter(0))[1]

    def inject_flow(self, src, dst, traffic_type='default'):
        priority = self.priority_map.get(traffic_type.lower(), 1)
        self.traffic[(src, dst)] = {'type': traffic_type, 'priority': priority}

        if dst in self.flow_tables.get(src, {}):
            path = self.flow_tables[src][dst]
            if path:
                print(f"Routing {traffic_type} flow from {src} to {dst} via {path}")
                for i in range(len(path) - 1):
                    self.link_utilization[(path[i], path[i + 1])] += 1
                    self.link_utilization[(path[i + 1], path[i])] += 1
            else:
                print(f"No available path for flow from {src} to {dst}")
        else:
            print(f"No routing information for {src} to {dst}")

    def _handle_link_failure(self, u, v):
        affected_flows = []
        for src in self.flow_tables:
            for dst, path in self.flow_tables[src].items():
                if path and any((u, v) == (path[i], path[i + 1]) or
                                (v, u) == (path[i], path[i + 1])
                                for i in range(len(path) - 1)):
                    affected_flows.append((src, dst))

        for src, dst in affected_flows:
            if (src, dst) in self.backup_paths and self.backup_paths[(src, dst)]:
                backup = self.backup_paths[(src, dst)].pop(0)
                self.flow_tables[src][dst] = backup
                print(f"Rerouted {src}-{dst} to backup path: {backup}")
                # Update utilization for new path
                for i in range(len(backup) - 1):
                    self.link_utilization[(backup[i], backup[i + 1])] += 1
                    self.link_utilization[(backup[i + 1], backup[i])] += 1
            else:
                print(f"No backup path available for {src}-{dst}")
                self.flow_tables[src][dst] = None

    def show_utilization(self):
        print("\nLink Utilization:")
        for (u, v), usage in self.link_utilization.items():
            capacity = self.topology.edges[u, v].get('capacity', 100)
            utilization_pct = (usage / capacity) * 100
            print(f"Link {u}-{v}: {usage}/{capacity} packets ({utilization_pct:.1f}%)")

    def show(self):
        pos = nx.spring_layout(self.topology)
        plt.figure(figsize=(10, 8))

        # Draw nodes and edges
        nx.draw_networkx_nodes(self.topology, pos, node_color='lightblue', node_size=500)
        nx.draw_networkx_edges(self.topology, pos, edge_color='gray', width=1)
        nx.draw_networkx_labels(self.topology, pos)

        # Draw edge weights
        edge_labels = nx.get_edge_attributes(self.topology, 'weight')
        nx.draw_networkx_edge_labels(self.topology, pos, edge_labels=edge_labels)

        # Highlight active flows
        for (src, dst), info in self.traffic.items():
            path = self.flow_tables.get(src, {}).get(dst)
            if path:
                edges = list(zip(path, path[1:]))
                color = 'red' if info['priority'] == 3 else \
                    'orange' if info['priority'] == 2 else 'green'
                nx.draw_networkx_edges(self.topology, pos, edgelist=edges,
                                       edge_color=color, width=2)

        plt.title("SDN Network Topology\n(Critical: Red, Important: Orange, Default: Green)")
        plt.show()


class SDNCLI(Cmd):
    controller = SDNController()

    def do_add_node(self, arg):
        nodes= arg.split()
        self.controller.add_node(*nodes)
        print(f"Node {arg} added.")

    def do_add_link(self, arg):
        args = arg.split()
        if len(args) < 2:
            print("Usage: add_link <node1> <node2> [weight=1] [capacity=100]")
            return

        u, v = args[0], args[1]
        weight = int(args[2]) if len(args) > 2 else 1
        capacity = int(args[3]) if len(args) > 3 else 100
        self.controller.add_link(u, v, weight, capacity)
        print(f"Link {u}-{v} added with weight {weight}, capacity {capacity}.")

    def do_remove_link(self, arg):
        args = arg.split()
        if len(args) != 2:
            print("Usage: remove_link <node1> <node2>")
            return

        u, v = args[0], args[1]
        self.controller.remove_link(u, v)

    def do_inject_flow(self, arg):
        args = arg.split()
        if len(args) < 2:
            print("Usage: inject_flow <src> <dst> [critical|important|default]")
            return

        src, dst = args[0], args[1]
        traffic_type = args[2] if len(args) > 2 else 'default'
        self.controller.inject_flow(src, dst, traffic_type)

    def do_fail_link(self, arg):

        args = arg.split()
        if len(args) != 2:
            print("Usage: fail_link <node1> <node2>")
            return

        u, v = args[0], args[1]
        self.controller.remove_link(u, v)

    def do_show_util(self, arg):
        self.controller.show_utilization()

    def do_show(self, arg):
        self.controller.show()

    def do_compute_paths(self, arg):
        self.controller.compute_paths()
        print("All paths recomputed.")

    def do_watermark(self, arg):
        #7e96a087bf275b6a79d3607b7ff01810f5fa9bc9ca1b839410d7fc1dedc4fd2b
        id = "899159756"
        watermark = id + "NeoDDaBRgX5a9"
        print(hashlib.sha256(watermark.encode()).hexdigest())

    def do_exit(self, arg):
        print("Exiting SDN controller.")
        return True

    def do_help(self, arg):
            print("\nSDN Controller Command List:")
            print("=" * 100)
            print("{:<20} {:<50}".format
        (   "Command                      ", "         Description"))
            print("-" * 100)
            commands = [
                ("add_node <n1> <n2> <n...>     ", "        Add nodes to the topology"),
                ("add_link <n1> <n2> [w] [c]    ", "        Add link between nodes (weight, capacity)"),
                ("remove_link <n1> <n2>         ", "        Remove a link between nodes"),
                ("inject_flow <src> <dst> [type]", "        Inject flow (critical/important/default)"),
                ("fail_link <n1> <n2>           ", "        Simulate link failure"),
                ("show_util                     ", "        Show link utilization statistics"),
                ("show                          ", "        Visualize the network"),
                ("compute_paths                 ", "        Recompute all paths"),
                ("watermark                     ", "        Show cryptographic watermark"),
                ("exit                          ", "        Exit the CLI")
            ]
            for cmd, desc in commands:
                print("{:<20} {:<30}".format(cmd, desc))


if __name__ == '__main__':
    print("SDN Controller Simulator")
    print("Type 'help' for available commands")
    SDNCLI().cmdloop()