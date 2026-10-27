import { memo, type ComponentProps, type ComponentType } from "react";
import { Linking, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import {
  isSafeHttpUrl,
  newsVerificationLabel,
  type TextNewsItem,
} from "../services/contentFeed";
import { colors } from "../theme";

type WebTextProps = ComponentProps<typeof Text> & {
  href?: string;
  hrefAttrs?: { rel?: string; target?: string };
};

const WebText = Text as ComponentType<WebTextProps>;

export function SourceLink({ href, children }: { href: string; children: string }) {
  if (!isSafeHttpUrl(href)) {
    return <Text style={styles.sourceName}>{children}</Text>;
  }
  if (Platform.OS === "web") {
    return (
      <WebText
        href={href}
        hrefAttrs={{ target: "_blank", rel: "noopener noreferrer" }}
        accessibilityRole="link"
        style={styles.link}
      >
        {children}
      </WebText>
    );
  }
  return (
    <Text
      accessibilityRole="link"
      style={styles.link}
      onPress={() => {
        void Linking.openURL(href);
      }}
    >
      {children}
    </Text>
  );
}

export const NewsItemCard = memo(function NewsItemCard({
  item,
  onOpen,
}: {
  item: TextNewsItem;
  onOpen?: () => void;
}) {
  const unverified = newsVerificationLabel(item.verified);
  return (
    <View style={styles.card}>
      <View style={styles.metaTop}>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>宗教动态</Text>
        </View>
        {unverified ? (
          <View style={styles.unverified}>
            <Text style={styles.unverifiedText}>{unverified}</Text>
          </View>
        ) : null}
        <Text style={styles.date}>{item.date}</Text>
      </View>
      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.excerpt}>{item.summary}</Text>
      <Text style={styles.region}>{item.region} · {item.category}</Text>
      <View style={styles.sourceRow}>
        <Text style={styles.sourceLabel}>来源：</Text>
        <SourceLink href={item.sourceUrl}>{item.sourceName}</SourceLink>
      </View>
      {onOpen ? (
        <Pressable accessibilityRole="button" onPress={onOpen} hitSlop={8}>
          <Text style={styles.more}>在本页查看摘要</Text>
        </Pressable>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.white,
    borderRadius: 18,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 15,
  },
  metaTop: { flexDirection: "row", alignItems: "center", gap: 9, flexWrap: "wrap" },
  badge: { borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: "#F3EFE4" },
  badgeText: { color: colors.greenDark, fontSize: 12, fontWeight: "700" },
  unverified: { borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: "#FFF4DA" },
  unverifiedText: { color: "#856417", fontSize: 12, fontWeight: "700" },
  date: { color: colors.inkSoft, fontSize: 12 },
  title: { color: colors.ink, fontSize: 17, fontWeight: "700", marginTop: 11 },
  excerpt: { color: colors.inkSoft, fontSize: 13, lineHeight: 20, marginTop: 5 },
  region: { color: colors.muted, fontSize: 12, marginTop: 8 },
  sourceRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", marginTop: 10 },
  sourceLabel: { color: colors.inkSoft, fontSize: 13 },
  sourceName: { color: colors.ink, fontSize: 13, fontWeight: "700" },
  link: { color: colors.green, fontSize: 13, fontWeight: "700", textDecorationLine: "underline" },
  more: { color: colors.green, fontSize: 12, fontWeight: "700", marginTop: 12 },
});
