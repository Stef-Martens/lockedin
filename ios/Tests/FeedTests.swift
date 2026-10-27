import HealthKit
import WorkoutKit
import XCTest
@testable import LockedIn

final class FeedTests: XCTestCase {
    private func sample() throws -> Feed {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "feed-sample", withExtension: "json"))
        return try decodeFeed(Data(contentsOf: url))
    }

    func testDecodesSample() throws {
        let feed = try sample()
        XCTAssertEqual(feed.today, "2026-10-27")
        XCTAssertEqual(feed.items.count, 2)
        let run = feed.items[0]
        XCTAssertEqual(run.workout.kind, "run")
        XCTAssertEqual(run.workout.blocks?.first?.iterations, 4)
        XCTAssertNil(run.note)
        XCTAssertNil(run.workout.cooldown?.alert)
        XCTAssertEqual(feed.items[1].note, "4 × 100 m, 30 s rest")
    }

    func testRunPlanShape() throws {
        let plan = try workoutPlan(for: try sample().items[0])
        guard case .custom(let run) = plan.workout else { return XCTFail("expected a custom workout") }
        XCTAssertEqual(run.activity, .running)
        XCTAssertEqual(run.displayName, "Tempo")
        XCTAssertEqual(run.blocks.count, 1)
        XCTAssertEqual(run.blocks[0].iterations, 4)
        XCTAssertEqual(run.blocks[0].steps.map(\.purpose), [.work, .recovery])
        XCTAssertNotNil(run.warmup)
        XCTAssertTrue(run.warmup?.alert is HeartRateRangeAlert)
        XCTAssertTrue(run.blocks[0].steps[0].step.alert is SpeedRangeAlert)
        XCTAssertEqual(run.cooldown?.goal, .open)
    }

    func testSwimPlanShape() throws {
        let plan = try workoutPlan(for: try sample().items[1])
        guard case .goal(let swim) = plan.workout else { return XCTFail("expected a single-goal workout") }
        XCTAssertEqual(swim.activity, .swimming)
        XCTAssertEqual(swim.swimmingLocation, .pool)
        XCTAssertEqual(swim.goal, .distance(1500, .meters))
    }

    func testDayLabels() {
        XCTAssertEqual(dayLabel("2026-10-27", today: "2026-10-27"), "Today")
        XCTAssertEqual(dayLabel("2026-10-28", today: "2026-10-27"), "Tomorrow")
        XCTAssertEqual(dayLabel("2026-10-29", today: "2026-10-27"), "Thu 29 Oct")
    }
}
