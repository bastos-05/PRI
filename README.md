# PRI

### REPORT
DOCX: https://docs.google.com/document/d/1EBQbp5Je-pxeZXom9qd25TjW5JFVIDhudJZfHjO6MJQ/edit?usp=sharing
<br>
LATEX: https://www.overleaf.com/1278562841tmsyzbzykhwz#cb4f79

### Templates
https://www.acm.org/publications/authors/submissions

Pipeline Config example
{
  "mode": "fresh",
  "crawler": {
    "workers": 3,
    "max_depth": 8
  },
  "filter": {
    "topics": [
      "Industrial disasters",
      "Structural failures",
      "Nuclear accidents",
      "Aviation accidents",
      "Natural disasters affecting infrastructure"
    ],
    "graph": {
      "min_parent_child_similarity": 0.6,
      "min_high_parent_ratio": 0.5
    }
  },
  "fetch": {
    "workers": 3,
    "batch_size": 20
  }
}