import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'airflow' / 'dags'))
from star_sdss_source import count_classes, smallest_class_rows

HEADER = 'objid,ra,dec,u,g,r,i,z,class,redshift\n'


def csv_with(*labels):
    rows = [f'{n},1,2,20,19,18,17,16,{label},0' for n, label in enumerate(labels)]
    return HEADER + '\n'.join(rows) + '\n'


class ClassCountTests(unittest.TestCase):
    def test_counts_rows_per_class_from_text_and_bytes(self):
        text = csv_with('STAR', 'STAR', 'GALAXY', 'QSO', 'STAR')
        expected = {'GALAXY': 1, 'QSO': 1, 'STAR': 3}
        self.assertEqual(count_classes(text), expected)
        self.assertEqual(count_classes(text.encode('utf-8')), expected)

    def test_missing_class_counts_zero_and_unknown_class_is_ignored(self):
        counts = count_classes(csv_with('STAR', 'STAR', 'GALAXY', 'OTRA'))
        self.assertEqual(counts, {'GALAXY': 1, 'QSO': 0, 'STAR': 2})
        self.assertEqual(smallest_class_rows(counts), 0)

    def test_labels_are_normalized_like_training(self):
        self.assertEqual(count_classes(csv_with(' star', 'Qso', 'GALAXY')),
                         {'GALAXY': 1, 'QSO': 1, 'STAR': 1})

    def test_smallest_class_rows(self):
        self.assertEqual(smallest_class_rows({'GALAXY': 40, 'QSO': 7, 'STAR': 100}), 7)
        self.assertEqual(smallest_class_rows({'STAR': 5}), 0)


if __name__ == '__main__':
    unittest.main()
