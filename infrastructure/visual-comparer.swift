import Foundation
import QuartzCore
import CoreGraphics
#if os(macOS)
import AppKit
#endif

func compareImages(path1: String, path2: String) -> Bool {
    #if os(macOS)
    guard let image1 = NSImage(contentsOfFile: path1),
          let image2 = NSImage(contentsOfFile: path2) else {
        print("Error: Could not load images")
        return false
    }

    guard image1.size == image2.size else {
        print("Error: Images have different sizes")
        return false
    }

    var rect = CGRect(origin: .zero, size: image1.size)
    guard let cgImage1 = image1.cgImage(forProposedRect: &rect, context: nil, hints: nil),
          let cgImage2 = image2.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
        return false
    }

    // Normalize comparison by drawing into a standard context
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let width = Int(image1.size.width)
    let height = Int(image1.size.height)
    let bytesPerPixel = 4
    let bytesPerRow = width * bytesPerPixel

    func createData(from cgImage: CGImage) -> Data? {
        guard let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: bytesPerRow, space: colorSpace, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return nil
        }
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))
        return context.data.map { Data(bytes: $0, count: height * bytesPerRow) }
    }

    guard let data1 = createData(from: cgImage1),
          let data2 = createData(from: cgImage2) else {
        return false
    }

    return data1 == data2
    #else
    print("Visual comparison only supported on macOS")
    return false
    #endif
}

let args = CommandLine.arguments
if args.count < 3 {
    print("Usage: visual-comparer <path1> <path2>")
    exit(1)
}

if compareImages(path1: args[1], path2: args[2]) {
    print("✅ Images are identical")
    exit(0)
} else {
    print("❌ Images differ")
    exit(1)
}
