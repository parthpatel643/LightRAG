# Line-Station Workspaces: Operations Notes

Operational notes for the line-station contract workspaces that this fork
builds locally and publishes to the AWS stores used by the `bos-line-stations`
app. Covers known infrastructure limits and data follow-ups that are tracked
but not yet scheduled.

## Publishing flow

1. Build the workspace locally (see `/ingest-workspace` and
   [Evaluation Guide](./EVALUATION_GUIDE.md)); publish only if the 3-run mean
   semantic-equivalence score is above 0.95.
2. Upload `data/<workspace>/` to
   `s3://bos-model-monitoring-data-artifacts/line_stations/<workspace>/`
   with `scripts/upload_to_s3.py`.
3. Queue the cloud load: `POST /bos-line-stations/api/batch-pipeline/workspaces`
   with `{"workspace": "<workspace>", "mode": "fresh"}` (admin token). The
   batch job writes a row to `bos_line_station.lightrag_runs`; check its
   status there.
4. Register the workspace in the app: `PUT
   /bos-line-stations/api/reference/systems/contract-library/stations/<STATION>/services/<service_type>`
   with `contract_number` and `vendor_name`. The app derives the workspace id
   as `<station>_<service_type>_<contract_number>` (lowercased), so the local
   workspace name must use the real contract number.

`scripts/migrate_storage.py` can push a workspace directly (`--mode fresh`)
and compare local and cloud copies (`--mode verify`); it reads the same
storage settings from `.env`.

## Open items

### OpenSearch Serverless access for direct pushes

The search index lives in the AOSS collection `bos-line-stations-cmk`
(endpoint in `neptune_opensearch_endpoint` of `bos-line-stations-lightrag-secret`).
Its data access policy, `bos-line-stations-policy`, grants index read/write only
to the pipeline and k8s roles (`bos-line-stations-k8s-role`,
`bos-feature-pipeline-job-role`, `bos-ml-applications-k8s-role`, and the L3
group).

The developer environment role `bos-mars-code-server-dev-role` is not in that
policy, so `migrate_storage.py --mode fresh` run from there writes MongoDB,
Milvus and Neptune but fails the OpenSearch step with 403. Use the batch
pipeline (step 3 above) instead, or add the role to the policy if direct pushes
are needed.

Status: open, to revisit.

### OpenSearch Serverless capacity

The account's AOSS capacity limits are 10 indexing OCUs and 10 search OCUs,
shared by every collection in the account. When the limit is reached, AOSS
returns HTTP 402 `service_quota_exceeded_exception` ("maximum OCU capacity
reached") for searches and indexing. This was seen on 2026-10-19 against an
existing line-station index, and the seven batch loads that failed on
2026-10-16 failed at the OpenSearch step in the same period.

Consider raising the account limits or reviewing other collections' usage if
this recurs, since the app's full-text graph search depends on these indexes.

Status: open, to revisit.

### Re-convert tables after the HTML-to-YAML converter fix

`scripts/html_table_to_yaml.py` used to keep only the first row header of each
table row and ignore `rowspan` on data cells (fixed in commit `c8a2f7957`). For
tables with two row headers (for example aircraft group plus service) this
dropped a value and shifted the rest one column left; rows under a
rowspanned data cell lost that value.

Re-running the fixed converter on the original HTML (`*.md.bak`) changes the
output for 33 files across most workspaces, for example a shifted
"Ramp Handling" row and missing equipment descriptions in
`cun_ground_handling_cw52444`. The published workspaces still pass the
evaluation gate, so nothing was rebuilt.

To fix a workspace: restore each `.md` from its `.bak`, re-run
`scripts/html_table_to_yaml.py inputs/<workspace>`, check widths and values
against the PDF, rebuild the graph, re-evaluate, upload, and queue a `fresh`
load. Workspaces built after the fix (`mco_cabin_cleaning_cw3611`,
`hnl_cabin_cleaning_cw71141`) already use it.

Status: open, optional.
