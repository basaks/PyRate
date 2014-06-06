'''
Tests for Minimum Spanning Tree (MST) functionality in PyRate
Author: Ben Davies, NCI
'''

import unittest
from numpy import empty, array, nan, isnan, sum as nsum
from itertools import product

from pyrate import algorithm
from pyrate.mst import mst_matrix, default_mst
from pyrate.tests.common import MockIfg, sydney5_mock_ifgs, sydney_data_setup


class MSTTests(unittest.TestCase):
	'''Basic verification of minimum spanning tree (MST) functionality.'''

	def setUp(self):
		self.ifgs = sydney_data_setup()
		self.epochs = algorithm.get_epochs(self.ifgs)


	def test_mst_matrix(self):
		# Verifies MST matrix func returns array with dict/trees in each cell
		for i in self.ifgs[3:]:
			i.phase_data[0,1] = 0 # add a large stack of nans to one cell

		for i in self.ifgs:
			i.convert_to_nans()

		res = mst_matrix(self.ifgs, self.epochs)
		ys, xs = res.shape
		for y, x in product(xrange(ys), xrange(xs)):
			r = res[y,x]
			num_nodes = len(r)
			self.assertTrue(num_nodes < len(self.epochs.dates))

			stack = array([i.phase_data[y,x] for i in self.ifgs]) # 17 ifg stack
			self.assertTrue(0 == nsum(stack == 0)) # all 0s should be converted
			nc = nsum(isnan(stack))

			if nc == 0:
				self.assertTrue(num_nodes == (len(self.epochs.dates) - 1))
			elif nc > 5:
				# rough test: too many nans must reduce the total tree size
				self.assertTrue(num_nodes <= (17-nc) )


	def test_partial_nan_pixel_stack(self):
		# Ensure a limited # of coherent cells results in a smaller MST tree
		num_coherent = 3

		def assert_equal():
			res = mst_matrix(mock_ifgs, self.epochs)
			self.assertEqual(len(res[0,0]), num_coherent)

		mock_ifgs = [MockIfg(i, 1, 1) for i in self.ifgs]
		for m in mock_ifgs[num_coherent:]:
			m.phase_data[:] = nan
		assert_equal()

		# fill in more nans leaving only one ifg
		for m in mock_ifgs[1:num_coherent]:
			m.phase_data[:] = nan
		num_coherent = 1
		assert_equal()


	def test_all_nan_pixel_stack(self):
		# ensure full stack of NaNs in an MST pixel classifies to NaN
		mock_ifgs = [MockIfg(i, 1, 1) for i in self.ifgs]
		for m in mock_ifgs:
			m.phase_data[:] = nan

		res = mst_matrix(mock_ifgs, self.epochs)
		exp = empty((1,1), dtype=object) 
		exp[:] = nan

		shape = (mock_ifgs[0].nrows, mock_ifgs[0].ncols)
		self.assertTrue(res.shape == shape)
		self.assertEqual(exp, res)



class DefaultMSTTests(unittest.TestCase):

	def test_default_mst(self):
		# default MST from full set of Ifgs shouldn't drop any nodes
		ifgs = sydney5_mock_ifgs()
		dates = [(i.master, i.slave) for i in ifgs]

		res = default_mst(ifgs)
		num_edges = len(res.keys())
		self.assertEqual(num_edges, len(ifgs))

		# test edges, note node order can be reversed
		for edge in res.iteritems():
			self.assertTrue(edge in dates or (edge[1],edge[0]) in dates)

		# check all nodes exist in this default tree
		mst_dates = set(res.keys() + res.values())
		for i in ifgs:
			for node in (i.master, i.slave):
				self.assertTrue(node in mst_dates)