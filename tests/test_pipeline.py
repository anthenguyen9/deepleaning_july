import unittest
from pipeline import mapped,convert,normalize

class DataTests(unittest.TestCase):
    def test_price_precedence(self):
        self.assertEqual(mapped('FOOD#PRICE#NEGATIVE'),'price:NEGATIVE')
    def test_location(self):
        self.assertEqual(mapped('LOCATION#GENERAL#POSITIVE'),'location:POSITIVE')
    def test_unknown(self):
        with self.assertRaises(ValueError): mapped('FOOD#QUALITY#BAD')
    def test_ignore_generic(self):
        self.assertIsNone(mapped('RESTAURANT#GENERAL#POSITIVE'))
    def test_span_validation(self):
        with self.assertRaises(ValueError): convert({'id':1,'data':'abc','label':[[0,8,'FOOD#QUALITY#POSITIVE']]})
    def test_preserve_conflicting_polarities(self):
        r=convert({'id':1,'data':'ngon dở','label':[[0,4,'FOOD#QUALITY#POSITIVE'],[5,7,'FOOD#QUALITY#NEGATIVE']]})
        self.assertEqual(len(r['labels']),2)
    def test_normalization(self):
        self.assertEqual(normalize('\ufeff ngon  quá '),'ngon quá')

if __name__=='__main__': unittest.main()
