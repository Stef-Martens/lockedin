import Foundation

/// The LockedIn watch feed (`GET /api/watch/runs`): today's and the next 7 days' planned runs and swims.
struct Feed: Decodable {
    let today: String
    let items: [FeedItem]
}

struct FeedItem: Decodable, Identifiable {
    let id: Int
    let day: String
    let sport: String
    let title: String
    let optional: Bool
    let note: String?
    let summary: String?
    let workout: FeedWorkout
}

/// A run (`kind: "run"`: warmup, blocks, cooldown) or a swim (`kind: "swim"`: one goal).
/// Fields are loose so that one item the app can't build doesn't stop the rest from decoding.
struct FeedWorkout: Decodable {
    let kind: String
    let displayName: String
    let location: String
    let warmup: FeedStep?
    let blocks: [FeedBlock]?
    let cooldown: FeedStep?
    let goal: FeedGoal?
}

struct FeedBlock: Decodable {
    let iterations: Int
    let steps: [FeedStep]
}

struct FeedStep: Decodable {
    let purpose: String?  // "work" or "recovery"; absent on warmup and cooldown
    let goal: FeedGoal
    let alert: FeedAlert?
}

/// `time` (seconds), `distance` (meters) or `open`.
struct FeedGoal: Decodable {
    let type: String
    let seconds: Double?
    let meters: Double?
}

/// `speed` (m/s range) or `heart_rate` (bpm range).
struct FeedAlert: Decodable {
    let type: String
    let minMps: Double?
    let maxMps: Double?
    let minBpm: Double?
    let maxBpm: Double?
}

enum FeedError: LocalizedError, Equatable {
    case noConnection
    case wrongKey
    case server(Int)
    case badData

    var errorDescription: String? {
        switch self {
        case .noConnection: "Can't reach LockedIn. Check the internet connection and the address in Settings."
        case .wrongKey: "LockedIn didn't accept the watch key. Check it in Settings."
        case .server(let status): "LockedIn had a problem (error \(status)). Try again in a minute."
        case .badData: "LockedIn sent something this app can't read. The app may be out of date: reinstall it with make ios."
        }
    }
}

func decodeFeed(_ data: Data) throws -> Feed {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    do {
        return try decoder.decode(Feed.self, from: data)
    } catch {
        throw FeedError.badData
    }
}

func fetchFeed(base: URL, key: String) async throws -> Feed {
    var request = URLRequest(url: base.appending(path: "api/watch/runs"))
    request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
    request.cachePolicy = .reloadIgnoringLocalCacheData
    let data: Data
    let response: URLResponse
    do {
        (data, response) = try await URLSession.shared.data(for: request)
    } catch let error as URLError where error.code == .cancelled {
        throw CancellationError()
    } catch {
        throw FeedError.noConnection
    }
    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
    switch status {
    case 200: return try decodeFeed(data)
    case 401: throw FeedError.wrongKey
    default: throw FeedError.server(status)
    }
}

/// "Today", "Tomorrow", else e.g. "Thu 30 Oct", counted from the server's today.
func dayLabel(_ day: String, today: String) -> String {
    guard let date = isoDay.date(from: day), let start = isoDay.date(from: today) else { return day }
    switch utcCalendar.dateComponents([.day], from: start, to: date).day {
    case 0: return "Today"
    case 1: return "Tomorrow"
    default: return shortDay.string(from: date)
    }
}

private let utcCalendar: Calendar = {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "UTC")!
    return calendar
}()

private let isoDay: DateFormatter = {
    let formatter = DateFormatter()
    formatter.calendar = utcCalendar
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = utcCalendar.timeZone
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
}()

private let shortDay: DateFormatter = {
    let formatter = DateFormatter()
    formatter.calendar = utcCalendar
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = utcCalendar.timeZone
    formatter.dateFormat = "EEE d MMM"
    return formatter
}()
