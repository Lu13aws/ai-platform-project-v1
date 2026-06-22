"""
Session 6A — Create CloudFront distribution + OAC for platform.bridging-data.com.

Run once:
    uv run python scripts/setup_platform_cloudfront.py
"""

import json
import boto3

REGION = "eu-central-1"
BUCKET = "platform.bridging-data.com"
DOMAIN = "platform.bridging-data.com"
CERT_ARN = "arn:aws:acm:us-east-1:759302162548:certificate/b1477709-fef7-46d6-8997-6da8e09e5a4f"
HOSTED_ZONE_ID = "Z07664873NC72578ZNY1H"


def main() -> None:
    cf = boto3.client("cloudfront")
    s3 = boto3.client("s3", region_name=REGION)
    r53 = boto3.client("route53")

    # Check if distribution already exists
    dists = cf.list_distributions()["DistributionList"].get("Items", [])
    existing = next(
        (d for d in dists if DOMAIN in d.get("Aliases", {}).get("Items", [])),
        None,
    )
    if existing:
        print(f"Distribution already exists: {existing['Id']} -> {existing['DomainName']}")
        cf_domain = existing["DomainName"]
        dist_id = existing["Id"]
    else:
        # Create Origin Access Control
        oac_resp = cf.create_origin_access_control(
            OriginAccessControlConfig={
                "Name": "platform-bridging-data-oac",
                "Description": "OAC for platform.bridging-data.com",
                "OriginAccessControlOriginType": "s3",
                "SigningBehavior": "always",
                "SigningProtocol": "sigv4",
            }
        )
        oac_id = oac_resp["OriginAccessControl"]["Id"]
        print(f"Created OAC: {oac_id}")

        dist_resp = cf.create_distribution(
            DistributionConfig={
                "CallerReference": "platform-bridging-data-2026",
                "Aliases": {"Quantity": 1, "Items": [DOMAIN]},
                "DefaultRootObject": "index.html",
                "Origins": {
                    "Quantity": 1,
                    "Items": [{
                        "Id": "s3-platform",
                        "DomainName": f"{BUCKET}.s3.{REGION}.amazonaws.com",
                        "S3OriginConfig": {"OriginAccessIdentity": ""},
                        "OriginAccessControlId": oac_id,
                    }],
                },
                "DefaultCacheBehavior": {
                    "TargetOriginId": "s3-platform",
                    "ViewerProtocolPolicy": "redirect-to-https",
                    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",  # CachingOptimized
                    "AllowedMethods": {
                        "Quantity": 2,
                        "Items": ["GET", "HEAD"],
                        "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
                    },
                    "Compress": True,
                },
                # SPA: 404/403 -> index.html (client-side routing)
                "CustomErrorResponses": {
                    "Quantity": 2,
                    "Items": [
                        {"ErrorCode": 404, "ResponsePagePath": "/index.html", "ResponseCode": "200", "ErrorCachingMinTTL": 0},
                        {"ErrorCode": 403, "ResponsePagePath": "/index.html", "ResponseCode": "200", "ErrorCachingMinTTL": 0},
                    ],
                },
                "Comment": "platform.bridging-data.com - AI Knowledge Platform",
                "Enabled": True,
                "HttpVersion": "http2",
                "PriceClass": "PriceClass_100",  # US + Europe only
                "ViewerCertificate": {
                    "ACMCertificateArn": CERT_ARN,
                    "SSLSupportMethod": "sni-only",
                    "MinimumProtocolVersion": "TLSv1.2_2021",
                },
            }
        )
        dist = dist_resp["Distribution"]
        dist_id = dist["Id"]
        cf_domain = dist["DomainName"]
        print(f"Created distribution: {dist_id} -> {cf_domain}")

    # Attach S3 bucket policy to allow CloudFront OAC
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "AllowCloudFrontOAC",
            "Effect": "Allow",
            "Principal": {"Service": "cloudfront.amazonaws.com"},
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{BUCKET}/*",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": f"arn:aws:cloudfront::759302162548:distribution/{dist_id}"
                }
            },
        }],
    }
    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(bucket_policy))
    print("S3 bucket policy updated for CloudFront OAC")

    # Route 53 alias record
    r53.change_resource_record_sets(
        HostedZoneId=HOSTED_ZONE_ID,
        ChangeBatch={
            "Changes": [{
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": DOMAIN,
                    "Type": "A",
                    "AliasTarget": {
                        "HostedZoneId": "Z2FDTNDATAQYW2",  # CloudFront hosted zone (always this)
                        "DNSName": cf_domain,
                        "EvaluateTargetHealth": False,
                    },
                },
            }],
        },
    )
    print(f"Route 53 A record: {DOMAIN} -> {cf_domain}")

    print(f"\n--- Done ---")
    print(f"CloudFront Distribution ID: {dist_id}")
    print(f"CloudFront Domain: {cf_domain}")
    print(f"Platform URL: https://{DOMAIN} (live in ~15 min after DNS propagates)")
    print(f"\nAdd to GitHub Actions secrets:")
    print(f"PLATFORM_CF_DISTRIBUTION_ID={dist_id}")


if __name__ == "__main__":
    main()
