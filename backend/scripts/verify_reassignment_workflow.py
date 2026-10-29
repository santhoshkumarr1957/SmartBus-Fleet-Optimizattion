import urllib.request
import json
import time
from app.db.session import SessionLocal
from app.models.bus import Bus
from app.models.route import Route
from app.models.reallocation_review import ReallocationReview
from app.models.reallocation_execution import ReallocationExecution
from app.services.optimization import OptimizationService
from app.schemas.optimization import ReallocationReviewCreate, ReallocationExecutionCreate

def main():
    print("=== TEST 2: ROUTE REASSIGNMENT & TRANSFER MOVEMENT ===")
    db = SessionLocal()
    try:
        # 1. State of buses in database
        buses = db.query(Bus).filter(Bus.status == "ACTIVE").all()
        print("Initial Buses in DB:")
        for b in buses:
            r_num = b.current_route.route_number if b.current_route else str(b.current_route_id)
            print(f"  Bus {b.bus_number} (ID: {b.id}) -> Route {r_num} (ID: {b.current_route_id}), Capacity: {b.capacity}")

        # 2. Query optimization overview and recommendations
        overview = OptimizationService.get_overview(db)
        print(f"\nOptimization Overview:")
        print(f"  Total Recommendations: {overview.total_recommendations}")
        print(f"  High: {overview.high_priority_count}, Medium: {overview.medium_priority_count}, Low: {overview.low_priority_count}")
        print(f"  Disclaimer: {overview.disclaimer}")
        if overview.diagnostic_reasons:
            print(f"  Diagnostic Reasons: {overview.diagnostic_reasons}")

        recs = OptimizationService.generate_recommendations(db)
        print(f"\nActive Recommendations: {len(recs)}")
        for r in recs:
            print(f"  {r.id}: Route {r.source_route_number} -> Route {r.target_route_number} (Bus {r.candidate_bus_number}), Score: {r.score}, Status: {r.feasibility_status}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
