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
        let location: HKWorkoutSessionLocationType = workout.location == "indoor" ? .indoor : .outdoor
        let run = CustomWorkout(
            activity: .running,
            location: location,
            displayName: workout.displayName,
            warmup: try workout.warmup.map { try workoutStep($0, location: location) },
            blocks: try blocks.map { try intervalBlock($0, location: location) },
            cooldown: try workout.cooldown.map { try workoutStep($0, location: location) }
        )
        return WorkoutPlan(.custom(run))
    case "swim":
        guard let goal = workout.goal else { throw PlanError(reason: "it has no goal") }
        let swimGoal = try workoutGoal(goal)
        guard SingleGoalWorkout.supportsGoal(swimGoal, activity: .swimming) else {
            throw PlanError(reason: "the watch can't take this swim's goal")
        }
        return WorkoutPlan(.goal(SingleGoalWorkout(activity: .swimming, swimmingLocation: .pool, goal: swimGoal)))
    default:
        throw PlanError(reason: "this app doesn't know \"\(workout.kind)\" workouts")
    }
}

private func intervalBlock(_ block: FeedBlock, location: HKWorkoutSessionLocationType) throws -> IntervalBlock {
    guard block.iterations >= 1, !block.steps.isEmpty else { throw PlanError(reason: "a repeat block is empty") }
    return IntervalBlock(steps: try block.steps.map { try intervalStep($0, location: location) }, iterations: block.iterations)
}

private func intervalStep(_ step: FeedStep, location: HKWorkoutSessionLocationType) throws -> IntervalStep {
    let purpose: IntervalStep.Purpose
    switch step.purpose {
    case "work": purpose = .work
    case "recovery": purpose = .recovery
    default: throw PlanError(reason: "a step is neither work nor recovery")
    }
    return IntervalStep(purpose, step: try workoutStep(step, location: location))
}

/// A step the watch can run: WorkoutKit says whether this goal and alert work for outdoor or indoor running.
private func workoutStep(_ step: FeedStep, location: HKWorkoutSessionLocationType) throws -> WorkoutStep {
    let goal = try workoutGoal(step.goal)
    guard CustomWorkout.supportsGoal(goal, activity: .running, location: location) else {
        throw PlanError(reason: "the watch can't end a running step that way")
    }
    let alert = try step.alert.map(workoutAlert)
    if let alert, !CustomWorkout.supportsAlert(alert, activity: .running, location: location) {
        throw PlanError(reason: "the watch can't warn about this pace or heart rate while running")
    }
    return WorkoutStep(goal: goal, alert: alert)
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
