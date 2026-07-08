DEFAULT_LOCATION = [37.436, 137.260]
DEFAULT_ZOOM = 14
DEFAULT_MAP_STYLE = "淡色地図"

MAP_STYLES = {
    "標準地図": {
        "url": "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
        "attr": "地理院地図 標準地図",
    },
    "淡色地図": {
        "url": "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png",
        "attr": "地理院地図 淡色地図",
    },
    "写真": {
        "url": "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg",
        "attr": "地理院地図 写真",
    },
}
