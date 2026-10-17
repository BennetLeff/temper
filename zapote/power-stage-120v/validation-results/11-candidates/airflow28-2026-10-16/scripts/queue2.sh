#!/bin/sh
# after the c28 top / zone searches: the x1.2 margin points, the 50 C air series, and the jet strip at the airflow-r1 design h
while pgrep -f "mode zone|mode top" >/dev/null; do sleep 30; done
python3 -I /Users/bennet/.claude/jobs/fbfc46b4/tmp/airflow28/scripts/airflow_search.py point --mode uniform --cases c28_h37@61,c28_h33@55 --max-workers 2
python3 -I /Users/bennet/.claude/jobs/fbfc46b4/tmp/airflow28/scripts/airflow_search.py search --series c28@50 --mode uniform --max-workers 2
python3 -I /Users/bennet/.claude/jobs/fbfc46b4/tmp/airflow28/scripts/airflow_search.py point --mode jet --cases c28_h10_jet60@55,c28_h10_jet100@55,c28_h10_jet60@61,c28_h10_jet100@61 --max-workers 2
