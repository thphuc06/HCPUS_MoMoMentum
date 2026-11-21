import boto3, time, datetime as dt
R = "ap-southeast-1"
cw = boto3.client("cloudwatch", region_name=R); rds = boto3.client("rds", region_name=R)
t0 = time.time()
while time.time() - t0 < 900:
    now = dt.datetime.now(dt.timezone.utc)
    m = cw.get_metric_statistics(Namespace="AWS/RDS", MetricName="ServerlessDatabaseCapacity",
        Dimensions=[{"Name": "DBInstanceIdentifier", "Value": "yofina-spike-db-inst1"}],
        StartTime=now - dt.timedelta(minutes=4), EndTime=now, Period=60, Statistics=["Average"])
    pts = sorted(m["Datapoints"], key=lambda x: x["Timestamp"])
    ev = rds.describe_events(SourceIdentifier="yofina-spike-db-inst1", SourceType="db-instance", Duration=30)["Events"]
    print(round(time.time() - t0), [round(p["Average"], 2) for p in pts][-3:], [e["Message"][:60] for e in ev][:2], flush=True)
    if pts and pts[-1]["Average"] == 0:
        print("PAUSED-metric", round(time.time() - t0), flush=True); break
    time.sleep(30)
