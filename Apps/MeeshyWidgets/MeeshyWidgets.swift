import WidgetKit
import SwiftUI

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> SimpleEntry {
        SimpleEntry(date: Date())
    }

    func getSnapshot(in context: Context, completion: @escaping (SimpleEntry) -> ()) {
        let entry = SimpleEntry(date: Date())
        completion(entry)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> ()) {
        let entries: [SimpleEntry] = [SimpleEntry(date: Date())]
        let timeline = Timeline(entries: entries, policy: .atEnd)
        completion(timeline)
    }
}

struct SimpleEntry: TimelineEntry {
    let date: Date
}

struct MeeshyWidgetsEntryView : View {
    var entry: Provider.Entry

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "shippingbox.fill")
                .font(.title2)
                .foregroundStyle(.tint)

            Text(entry.date, style: .time)
                .font(.system(.title, design: .rounded).bold())
                .minimumScaleFactor(0.5)
                .lineLimit(1)
        }
        .containerBackground(.background, for: .widget)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Meeshy Platform Status")
    }
}

@main
struct MeeshyWidgets: Widget {
    let kind: String = "MeeshyWidgets"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: Provider()) { entry in
            MeeshyWidgetsEntryView(entry: entry)
        }
        .configurationDisplayName("Meeshy Status")
        .description("Stay updated with your Meeshy delivery platform status.")
    }
}
