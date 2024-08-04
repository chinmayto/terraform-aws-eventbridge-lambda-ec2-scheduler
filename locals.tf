locals {
  common_tags = {
    company     = var.company
    project     = "${var.company}-${var.project}"
    environment = var.environment
  }

  naming_prefix = "${var.naming_prefix}-${var.environment}"
}

locals {
  scheduler_actions = {
    stop  = var.stop_cron_schedule
    start = var.start_cron_schedule
  }
}