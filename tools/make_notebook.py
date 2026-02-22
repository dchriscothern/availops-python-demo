import json
from pathlib import Path

root = Path(r"C:\GitHub\availops-python-demo\availops-python-demo")
nb_path = root / "notebooks" / "AvailOps_Demo_Analysis.ipynb"
nb_path.parent.mkdir(parents=True, exist_ok=True)

cells = [
  {"cell_type":"markdown","metadata":{}, "source":[
    "# AvailOps Demo Analysis (Python)\n",
    "\n",
    "Loads demo CSVs from `demo_data/`, validates schema, and generates simple plots.\n",
    "\n",
    "**Data note:** demo/anonymized only.\n"
  ]},
  {"cell_type":"code","metadata":{}, "execution_count":None,"outputs":[], "source":[
    "from pathlib import Path\n",
    "import pandas as pd\n",
    "import matplotlib.pyplot as plt\n",
    "\n",
    "ROOT = Path.cwd()\n",
    "DATA = ROOT / 'demo_data'\n",
    "\n",
    "def read_csv_robust(path: Path) -> pd.DataFrame:\n",
    "    if not path.exists():\n",
    "        return pd.DataFrame()\n",
    "    try:\n",
    "        df = pd.read_csv(path)\n",
    "        if df.shape[1] > 1:\n",
    "            return df\n",
    "    except Exception:\n",
    "        pass\n",
    "    df = pd.read_csv(path)\n",
    "    col0 = df.columns[0]\n",
    "    s = df[col0].astype(str).str.strip()\n",
    "    split = s.str.split(',', expand=True)\n",
    "    if split.shape[1] > 1:\n",
    "        split.columns = split.iloc[0]\n",
    "        out = split.iloc[1:].reset_index(drop=True)\n",
    "        return out\n",
    "    return pd.read_csv(path, sep=';')\n",
    "\n",
    "watch = read_csv_robust(DATA/'watchlist_today.csv')\n",
    "trends = read_csv_robust(DATA/'team_trends_7d.csv')\n",
    "public = read_csv_robust(DATA/'public_wnba_2025_DAL_availability_anon.csv')\n",
    "\n",
    "print('watch:', watch.shape)\n",
    "print('trends:', trends.shape)\n",
    "print('public:', public.shape)\n",
    "\n",
    "watch.head(10)\n"
  ]}
]

nb = {
  "cells": cells,
  "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
  "nbformat": 4,
  "nbformat_minor": 5
}

nb_path.write_text(json.dumps(nb, indent=2), encoding="utf-8")
print("Wrote notebook:", nb_path)