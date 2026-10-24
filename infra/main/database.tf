resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "Postgres: app server only"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-db" }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  description                  = "Postgres from the app server"
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

# RDS rejects '/', '@', '"' and space in master passwords; '$', '#' and '\''
# are excluded too so the value survives the compose .env file unescaped.
resource "random_password" "db" {
  length           = 40
  special          = true
  override_special = "-_.!*~+="
}

# The app's migrations create btree_gist, pg_trgm and (later) vector; all three
# are on the RDS for PostgreSQL 17 extension list and the master user (who
# runs migrations) has rds_superuser.
resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "17" # major only: RDS picks the default minor, auto-upgraded
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "clearpath"
  username = "clearpath"
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period = var.db_backup_retention_days
  backup_window           = "07:00-07:30" # 2-3am US Eastern
  maintenance_window      = "sun:07:30-sun:08:30"
  copy_tags_to_snapshot   = true

  auto_minor_version_upgrade = true
  apply_immediately          = true

  # Never silently enroll in paid Extended Support when 17 leaves standard support.
  engine_lifecycle_support = "open-source-rds-extended-support-disabled"

  deletion_protection       = false
  skip_final_snapshot       = var.db_skip_final_snapshot
  final_snapshot_identifier = var.db_skip_final_snapshot ? null : "${local.name}-final"
}
