#!/usr/bin/env bash
# Render /srv/clearpath/.env from SSM Parameter Store. Runs on the app server
# (instance role credentials) at every deploy.
#
#   render-env.sh <backend-image-ref>
#
# Every direct child of $SSM_PREFIX becomes KEY='value' (Terraform writes the
# config values and secrets there; ANTHROPIC_API_KEY is set by hand).
# $SSM_PREFIX/deploy/* are inputs to this script, not app settings.
set -euo pipefail

image="${1:?usage: render-env.sh <backend-image-ref>}"
prefix="${SSM_PREFIX:-/clearpath/prod}"
out="${ENV_OUT:-/srv/clearpath/.env}"

imds_token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
region=$(curl -fsS -H "X-aws-ec2-metadata-token: ${imds_token}" \
  http://169.254.169.254/latest/meta-data/placement/region)

tmp=$(mktemp "${out}.XXXXXX")
trap 'rm -f "$tmp"' EXIT
chmod 600 "$tmp"

# Single quotes make compose's env-file parser take the value literally (no
# $-interpolation, '#' isn't a comment). A value containing a quote or a
# newline can't be represented that way, so fail rather than corrupt it.
emit() {
  local key="$1" value="$2"
  if [[ ! "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
    echo "render-env: '${key}' is not a valid env var name; refusing" >&2
    exit 1
  fi
  if [[ "$value" == *"'"* || "$value" == *$'\n'* ]]; then
    echo "render-env: ${key} contains a single quote or newline; refusing" >&2
    exit 1
  fi
  printf "%s='%s'\n" "$key" "$value" >>"$tmp"
}

# Non-recursive: only $prefix/KEY, not $prefix/deploy/KEY. The CLI follows
# NextToken itself. Values travel base64-encoded through the pipe so no byte
# in them can be mangled by word splitting or jq's escaping.
params=$(aws ssm get-parameters-by-path --region "$region" --path "$prefix" \
  --with-decryption --output json)
count=0
while read -r key value_b64; do
  emit "$key" "$(base64 -d <<<"$value_b64")"
  count=$((count + 1))
done < <(jq -r '.Parameters[] | "\(.Name | split("/") | last) \(.Value | @base64)"' <<<"$params")

if ((count == 0)); then
  echo "render-env: no parameters under ${prefix}" >&2
  exit 1
fi

deploy_param() {
  aws ssm get-parameter --region "$region" --name "${prefix}/deploy/$1" \
    --query Parameter.Value --output text
}

# uvicorn --forwarded-allow-ips: the live CloudFront origin-facing ranges plus
# the VPC CIDR (see compose.prod.yaml for why not "*"). Re-read on every
# deploy so new CloudFront ranges are picked up without a Terraform apply.
vpc_cidr=$(deploy_param VPC_CIDR)
prefix_list_id=$(deploy_param CLOUDFRONT_PREFIX_LIST_ID)
cloudfront_cidrs=$(aws ec2 get-managed-prefix-list-entries --region "$region" \
  --prefix-list-id "$prefix_list_id" --query 'Entries[].Cidr' --output json |
  jq -r 'join(",")')
if [[ -z "$cloudfront_cidrs" ]]; then
  echo "render-env: prefix list ${prefix_list_id} returned no entries" >&2
  exit 1
fi

emit FORWARDED_ALLOW_IPS "${vpc_cidr},${cloudfront_cidrs}"
emit BACKEND_IMAGE "$image"

mv -f "$tmp" "$out"
trap - EXIT
echo "render-env: wrote $((count + 2)) keys to ${out}"
