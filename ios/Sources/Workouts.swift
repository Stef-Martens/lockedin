import Foundation
import HealthKit
import WorkoutKit

/// Why one run or swim can't go to the watch. The others still can.
struct PlanError: LocalizedError {
    let reason: String
    var errorDescription: String? { "Can't put this on the watch: \(reason)." }
}

/// A run becomes a `CustomWorkout` with its steps and alerts; a swim a pool swim with one goal.
func workoutPlan(for item: FeedItem) throws -> WorkoutPlan {
    let workout = item.workout
    switch workout.kind {
    case "run":
        guard let blocks = workout.blocks, !blocks.isEmpty else { throw PlanError(reason: "it has no steps") }
        let run = CustomWorkout(
            activity: .running,
            location: workout.location == "indoor" ? .indoor : .outdoor,
            displayName: workout.displayName,
            warmup: try workout.warmup.map(workoutStep),
            blocks: try blocks.map(intervalBlock),
            cooldown: try workout.cooldown.map(workoutStep)
        )
        return WorkoutPlan(.custom(run))
    case "swim":
        guard let goal = workout.goal else { throw PlanError(reason: "it has no goal") }
        return WorkoutPlan(.goal(SingleGoalWorkout(activity: .swimming, swimmingLocation: .pool,
                                                   goal: try workoutGoal(goal))))
    default:
        throw PlanError(reason: "this app doesn't know \"\(workout.kind)\" workouts")
    }
}

private func intervalBlock(_ block: FeedBlock) throws -> IntervalBlock {
    guard block.iterations >= 1, !block.steps.isEmpty else { throw PlanError(reason: "a repeat block is empty") }
    return IntervalBlock(steps: try block.steps.map(intervalStep), iterations: block.iterations)
}

private func intervalStep(_ step: FeedStep) throws -> IntervalStep {
    let purpose: IntervalStep.Purpose
    switch step.purpose {
    case "work": purpose = .work
    case "recovery": purpose = .recovery
    default: throw PlanError(reason: "a step is neither work nor recovery")
    }
    return IntervalStep(purpose, step: try workoutStep(step))
}

private func workoutStep(_ step: FeedStep) throws -> WorkoutStep {
    WorkoutStep(goal: try workoutGoal(step.goal), alert: try step.alert.map(workoutAlert))
}

private func workoutGoal(_ goal: FeedGoal) throws -> WorkoutGoal {
    switch goal.type {
    case "open":
        return .open
    case "time":
        guard let seconds = goal.seconds, seconds > 0 else { break }
        return .time(seconds, .seconds)
    case "distance":
        guard let meters = goal.meters, meters > 0 else { break }
        return .distance(meters, .meters)
    default:
        break
    }
    throw PlanError(reason: "a step's length isn't a time, a distance or open")
}

private func workoutAlert(_ alert: FeedAlert) throws -> any WorkoutAlert {
    switch alert.type {
    case "speed":
        guard let low = alert.minMps, let high = alert.maxMps, low > 0, low <= high else { break }
        let range = Measurement(value: low, unit: UnitSpeed.metersPerSecond)...Measurement(value: high, unit: .metersPerSecond)
        return SpeedRangeAlert(target: range, metric: .current)
    case "heart_rate":
        guard let low = alert.minBpm, let high = alert.maxBpm, low > 0, low <= high else { break }
        return HeartRateRangeAlert.heartRate(low...high)
    default:
        break
    }
    throw PlanError(reason: "a pace or heart-rate target is out of shape")
}
