# STRATUS 3-run stability report (repaired)

- Successful runs: 3/3
- First-attempt successes: 3/3
- Mean TTM: 1618.199 s
- Median TTM: 873.661 s
- TTM range: 500.839–3480.096 s
- Mean steps: 8.000
- Total input tokens: 116902
- Total output tokens: 442
- Executed dangerous operations: 0
- Functional stability gate: **PASS**

|Run|Status|Success|TTM(s)|Steps|In tok|Out tok|First attempt|Retry|Format retries|Danger|Last object|Port verified|
|---:|---|:---:|---:|---:|---:|---:|:---:|:---:|---:|---:|---|:---:|
|1|SUCCESS|True|500.83915424346924|9|34684|161|True|False|1|0|Service/test-social-network/user-service|True|
|2|SUCCESS|True|873.6609148979187|8|47620|148|True|False|1|0|Service/test-social-network/user-service|True|
|3|SUCCESS|True|3480.096101999283|7|34598|133|True|False|9|0|Service/test-social-network/user-service|True|
