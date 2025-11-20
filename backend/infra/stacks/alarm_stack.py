"""
CloudWatch Alarm Stack - 30-Minute Idle Detection

Creates CloudWatch Alarm that:
- Monitors SQS queue ApproximateNumberOfMessagesVisible metric
- Triggers when queue is empty (0 messages) for 30 minutes
- Invokes Lambda function to shutdown GPU instance
"""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
)
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class AlarmStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        queue: sqs.Queue,
        lambda_function: lambda_.Function,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudWatch Metric: ApproximateNumberOfMessagesVisible
        queue_visible_messages_metric = queue.metric_approximate_number_of_messages_visible(
            # Metric statistics
            statistic=cloudwatch.Stats.AVERAGE,
            # Evaluation period (5 minutes)
            period=Duration.minutes(5),
        )

        # CloudWatch Alarm
        self.queue_empty_alarm = cloudwatch.Alarm(
            self,
            "QueueEmptyFor30Min",
            alarm_name="QueueEmptyFor30Min",
            alarm_description=(
                "Triggers GPU instance shutdown when SQS queue has been "
                "empty (0 visible messages) for 30 minutes continuously"
            ),
            # Metric to monitor
            metric=queue_visible_messages_metric,
            # Threshold: 0 messages
            threshold=0,
            # Comparison operator
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
            # Evaluation periods: 6 periods × 5 minutes = 30 minutes
            evaluation_periods=6,
            # Datapoints to alarm: All 6 datapoints must breach
            datapoints_to_alarm=6,
            # Treat missing data as "not breaching"
            # This prevents false alarms if metrics are temporarily unavailable
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Create SNS topic to trigger Lambda (CloudWatch Alarms cannot directly invoke Lambda)
        # The alarm triggers SNS, which then invokes Lambda
        alarm_topic = sns.Topic(
            self,
            "AlarmTopic",
            topic_name="gpu-shutdown-alerts",
            display_name="GPU Auto-Shutdown Alerts"
        )

        # Subscribe Lambda to SNS topic
        alarm_topic.add_subscription(
            subscriptions.LambdaSubscription(lambda_function)
        )

        # Add SNS as alarm action
        self.queue_empty_alarm.add_alarm_action(
            cw_actions.SnsAction(alarm_topic)
        )

        # Outputs
        CfnOutput(
            self,
            "AlarmName",
            value=self.queue_empty_alarm.alarm_name,
            description="Name of the CloudWatch Alarm",
            export_name=f"{construct_id}-AlarmName"
        )

        CfnOutput(
            self,
            "AlarmArn",
            value=self.queue_empty_alarm.alarm_arn,
            description="ARN of the CloudWatch Alarm",
            export_name=f"{construct_id}-AlarmArn"
        )
