import collections
import unittest
from resistor_layout import build, parse_counts


def intersects(s,t):
    a,b=s['points']; c,d=t['points']
    return (max(min(a[0],b[0]),min(c[0],d[0])) <= min(max(a[0],b[0]),max(c[0],d[0])) and
            max(min(a[1],b[1]),min(c[1],d[1])) <= min(max(a[1],b[1]),max(c[1],d[1])))


class LayoutTest(unittest.TestCase):
    def verify_layout(self,l,counts,centroid):
        actual=collections.Counter(c['group'] for c in l['cells'] if c['group']!='D')
        self.assertEqual(actual,counts)
        if centroid: self.assertLess(l['max_centroid_separation'],1e-9)
        cells={c['id']:c for c in l['cells']}
        seen=collections.Counter(t for r in l['routes'] for t in r['terminals'])
        for c in cells.values():
            if c['group']!='D':
                for pin in ['P','N']: self.assertEqual(seen[f'{c["id"]}.{pin}'],1)
            if c['row'] in (0,l['rows']+1) or c['col'] in (0,l['columns']+1):
                self.assertEqual(c['group'],'D')
        # No same-layer centerline shorts between different nets.
        segments=[(r['net'],s) for r in l['routes'] for s in r['segments']]
        for i,(net,s) in enumerate(segments):
            for other,t in segments[i+1:]:
                if net!=other and s['layer']==t['layer']:
                    self.assertFalse(intersects(s,t),(net,other,s,t))
        # Every routed net is connected through its segments and explicit vias.
        for r in l['routes']:
            adj=collections.defaultdict(set)
            def edge(a,b): adj[a].add(b); adj[b].add(a)
            for s in r['segments']:
                edge((s['layer'],*s['points'][0]),(s['layer'],*s['points'][1]))
            for v in r['vias']: edge((v['layers'][0],*v['at']),(v['layers'][1],*v['at']))
            reached=set(); stack=[next(iter(adj))]
            while stack:
                q=stack.pop()
                if q not in reached: reached.add(q); stack.extend(adj[q]-reached)
            self.assertEqual(reached,set(adj))
            for term in r['terminals']:
                name,pin=term.rsplit('.',1)
                self.assertIn(('M1',*cells[name]['pins'][pin]),reached)
        for g,cnt in counts.items():
            nets=[r for r in l['routes'] if r['group']==g]
            self.assertEqual(len(nets),cnt+1)
            self.assertEqual(sum(r['port'] is not None for r in nets),2)

    def test_centroid_and_routing(self):
        for counts in [{'A':4,'B':4},{'A':2,'B':6},{'A':4,'B':8,'C':4}]:
            for cols in [1,3,4,7]: self.verify_layout(build(counts,cols),counts,True)

    def test_odd_interdigitated(self):
        c={'A':3,'B':5}; self.verify_layout(build(c,3,'interdigitated'),c,False)

    def test_validation(self):
        for s in ['A:0','A:2,A:4','D:2','A-:2']:
            with self.assertRaises(ValueError): parse_counts(s)
        with self.assertRaises(ValueError): build({'A':3})
        with self.assertRaises(ValueError): build({'A':2},0)

if __name__=='__main__': unittest.main()
