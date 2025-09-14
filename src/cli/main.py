"""CLI interface for VQE prediction system."""

import argparse
import asyncio
import json
import sys
from typing import List

from src.services.vqe_predictor import VQEPredictor, PredictionRequest
from src.services.data_loader import DataLoader
from src.services.report_service import ReportService
from src.services.export_service import ExportService
from src.models import ReportCreateRequest


def predict_command(args):
    """Handle prediction command."""
    try:
        # Load data
        data_loader = DataLoader()
        if args.data_file.endswith(".csv"):
            raw_data = data_loader.load_csv_data(args.data_file)
        elif args.data_file.endswith(".json"):
            raw_data = data_loader.load_json_data(args.data_file)
        else:
            print("Error: Data file must be .csv or .json")
            return 1

        # Validate data
        errors = data_loader.validate_data(raw_data, args.min_years)
        if errors:
            print("Data validation errors:")
            for error in errors:
                print(f"  - {error}")
            return 1

        # Prepare historical data for prediction
        historical_data = {}
        for topic in args.topics:
            frequencies = data_loader.get_topic_frequencies(raw_data, topic)
            if frequencies:
                historical_data[topic] = frequencies

        if not historical_data:
            print("Error: No valid historical data found for requested topics")
            return 1

        # Create prediction request
        request = PredictionRequest(
            topics=args.topics,
            historical_years=args.historical_years,
            confidence_level=args.confidence,
            force_classical=args.force_classical,
        )

        # Initialize predictor and make predictions
        predictor = VQEPredictor()
        response = predictor.predict_topics(request, historical_data)

        # Display results
        print(f"\nPrediction Results (Execution time: {response.execution_time_ms}ms)")
        print(f"Fallback used: {response.fallback_used}")
        print("-" * 60)

        for prediction in response.predictions:
            print(f"Topic: {prediction.topic}")
            print(".4f")
            print(".4f")
            print(f"Trend: {prediction.trend}")
            print(f"Method: {prediction.method}")
            print("-" * 30)

        # Save results if requested
        if args.output:
            output_data = {
                "predictions": [
                    {
                        "topic": p.topic,
                        "importance": p.importance,
                        "confidence_interval": list(p.confidence_interval),
                        "trend": p.trend,
                        "method": p.method,
                    }
                    for p in response.predictions
                ],
                "execution_time_ms": response.execution_time_ms,
                "fallback_used": response.fallback_used,
            }

            with open(args.output, "w") as f:
                json.dump(output_data, f, indent=2)
            print(f"\nResults saved to: {args.output}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def list_topics_command(args):
    """Handle list topics command."""
    try:
        # Load data
        data_loader = DataLoader()
        if args.data_file.endswith(".csv"):
            raw_data = data_loader.load_csv_data(args.data_file)
        elif args.data_file.endswith(".json"):
            raw_data = data_loader.load_json_data(args.data_file)
        else:
            print("Error: Data file must be .csv or .json")
            return 1

        # Get available topics
        topics = data_loader.get_available_topics(raw_data, args.min_years)

        print(f"\nAvailable Topics (minimum {args.min_years} years of data):")
        print("-" * 50)

        for topic in topics:
            print(f"ID: {topic['id']}")
            print(f"Name: {topic['name']}")
            print(f"Years available: {topic['years_available']}")
            print(f"Latest year: {topic['latest_year']}")
            print("-" * 30)

        print(f"\nTotal topics: {len(topics)}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def generate_report_command(args):
    """Handle report generation command."""
    try:
        # Initialize services
        report_service = ReportService()

        # Create report request
        request = ReportCreateRequest(
            title=args.title,
            description=args.description,
            topics=args.topics,
            prediction_year=args.prediction_year,
            confidence_threshold=args.confidence_threshold
        )

        # Create report
        report = report_service.create_report(request)

        print(f"Report created successfully!")
        print(f"Report ID: {report.id}")
        print(f"Title: {report.title}")
        print(f"Topics: {', '.join(report.topics)}")
        print(f"Status: {report.status}")

        # Generate report data if requested
        if args.generate_now:
            print("\nGenerating report data...")
            # Run async function in sync context
            async def generate():
                return await report_service.generate_report_data(report.id)

            success = asyncio.run(generate())
            if success:
                print("Report generation completed!")
                report = report_service.get_report(report.id)
                print(f"Updated status: {report.status}")
            else:
                print("Report generation failed. Check logs for details.")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def export_report_command(args):
    """Handle report export command."""
    try:
        # Initialize services
        report_service = ReportService()
        export_service = ExportService()

        # Check if report exists
        report = report_service.get_report(args.report_id)
        if not report:
            print(f"Error: Report {args.report_id} not found")
            return 1

        print(f"Exporting report: {report.title}")
        print(f"Format: {args.format}")

        # Get report data and visualizations
        data = report_service.get_report_data(args.report_id)
        visualizations = report_service.get_report_visualizations(args.report_id)

        # Export based on format
        if args.format == "pdf":
            file_path = export_service.export_pdf(report, data, visualizations)
        elif args.format == "csv":
            file_path = export_service.export_csv(report, data)
        elif args.format == "json":
            file_path = export_service.export_json(report, data, visualizations)
        else:
            print(f"Error: Unsupported format {args.format}")
            return 1

        print(f"Export completed successfully!")
        print(f"File saved to: {file_path}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="VQE Exam Topic Prediction System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Predict topics using CSV data
  python -m src.cli.main predict quantum-mechanics linear-algebra \\
    --data-file data/exam_data.csv

  # List available topics
  python -m src.cli.main list-topics --data-file data/exam_data.csv

  # Create and generate a report
  python -m src.cli.main generate-report "Quantum Topics Report" \\
    "Analysis of quantum topics" quantum-mechanics quantum-algorithms \\
    --generate-now

  # Export a report
  python -m src.cli.main export-report report_12345 --format pdf

  # Force classical prediction
  python -m src.cli.main predict quantum-mechanics \\
    --data-file data/exam_data.csv --force-classical
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Predict command
    predict_parser = subparsers.add_parser("predict", help="Predict topic importance")
    predict_parser.add_argument("topics", nargs="+", help="Topics to predict")
    predict_parser.add_argument(
        "--data-file",
        required=True,
        help="Path to historical data file (.csv or .json)",
    )
    predict_parser.add_argument(
        "--historical-years",
        type=int,
        default=5,
        help="Number of historical years to use",
    )
    predict_parser.add_argument(
        "--confidence", type=float, default=0.95, help="Confidence level (0-1)"
    )
    predict_parser.add_argument(
        "--force-classical", action="store_true", help="Force classical prediction"
    )
    predict_parser.add_argument(
        "--min-years", type=int, default=3, help="Minimum years of data required"
    )
    predict_parser.add_argument("--output", help="Output file for results (JSON)")

    # List topics command
    list_parser = subparsers.add_parser("list-topics", help="List available topics")
    list_parser.add_argument(
        "--data-file",
        required=True,
        help="Path to historical data file (.csv or .json)",
    )
    list_parser.add_argument(
        "--min-years", type=int, default=3, help="Minimum years of data required"
    )

    # Generate report command
    generate_parser = subparsers.add_parser("generate-report", help="Create and optionally generate a report")
    generate_parser.add_argument("title", help="Report title")
    generate_parser.add_argument("description", help="Report description")
    generate_parser.add_argument("topics", nargs="+", help="Topics to analyze")
    generate_parser.add_argument(
        "--prediction-year", type=int, default=2025, help="Year to predict for"
    )
    generate_parser.add_argument(
        "--confidence-threshold", type=float, default=0.8, help="Confidence threshold"
    )
    generate_parser.add_argument(
        "--generate-now", action="store_true", help="Generate report data immediately"
    )

    # Export report command
    export_parser = subparsers.add_parser("export-report", help="Export a report to file")
    export_parser.add_argument("report_id", help="Report ID to export")
    export_parser.add_argument(
        "--format", choices=["pdf", "csv", "json"], default="pdf", help="Export format"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "predict":
        return predict_command(args)
    elif args.command == "list-topics":
        return list_topics_command(args)
    elif args.command == "generate-report":
        return generate_report_command(args)
    elif args.command == "export-report":
        return export_report_command(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
