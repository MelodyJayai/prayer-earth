import Ionicons from "@expo/vector-icons/Ionicons";
import { useMemo, useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { PRAYER_CATEGORIES, type PrayerCategory } from "../domain/types";
import { colors } from "../theme";

type Props = {
  visible: boolean;
  asModal?: boolean;
  onClose: () => void;
  onOpenGuidelines?: () => void;
  onPublish: (input: {
    title: string;
    excerpt: string;
    category: PrayerCategory;
  }) => void;
};

export function PrayerComposer({
  visible,
  asModal = true,
  onClose,
  onOpenGuidelines,
  onPublish,
}: Props) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [category, setCategory] = useState<PrayerCategory>("家庭");
  const [accepted, setAccepted] = useState(false);
  const canPublish = useMemo(
    () => title.trim().length >= 4 && body.trim().length >= 8 && accepted,
    [accepted, body, title],
  );

  const reset = () => {
    setTitle("");
    setBody("");
    setCategory("家庭");
    setAccepted(false);
  };

  const close = () => {
    reset();
    onClose();
  };

  const publish = () => {
    if (!canPublish) return;
    onPublish({ title: title.trim(), excerpt: body.trim(), category });
    reset();
  };

  const content = (
    <SafeAreaView style={styles.modal} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.flex}
      >
        <View style={styles.header}>
          <Pressable accessibilityRole="button" onPress={close} hitSlop={8}>
            <Text style={styles.cancel}>取消</Text>
          </Pressable>
          <Text accessibilityRole="header" style={styles.headerTitle}>
            发布祷告
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !canPublish }}
            disabled={!canPublish}
            hitSlop={8}
            onPress={publish}
          >
            <Text style={[styles.publish, !canPublish && styles.disabled]}>
              发布
            </Text>
          </Pressable>
        </View>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.form}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.formIcon}>
            <Ionicons name="heart" size={27} color={colors.green} />
          </View>
          <Text style={styles.title}>让我们与你一同祷告</Text>
          <Text style={styles.hint}>
            请避免填写真实姓名、联系方式等敏感个人信息。
          </Text>
          <Text style={styles.label}>祷告类型</Text>
          <View style={styles.categories}>
            {PRAYER_CATEGORIES.map((item) => (
              <Pressable
                accessibilityRole="radio"
                accessibilityState={{ checked: category === item }}
                key={item}
                onPress={() => setCategory(item)}
                style={[
                  styles.category,
                  category === item && styles.categoryActive,
                ]}
              >
                <Text
                  style={[
                    styles.categoryText,
                    category === item && styles.categoryTextActive,
                  ]}
                >
                  {item}
                </Text>
              </Pressable>
            ))}
          </View>
          <Text style={styles.label}>祷告主题</Text>
          <TextInput
            accessibilityLabel="祷告主题"
            value={title}
            onChangeText={setTitle}
            placeholder="例如：为家人的健康祷告"
            placeholderTextColor={colors.muted}
            style={styles.input}
            maxLength={60}
            returnKeyType="next"
          />
          <Text style={styles.label}>祷告内容</Text>
          <TextInput
            accessibilityLabel="祷告内容"
            value={body}
            onChangeText={setBody}
            placeholder="写下你希望大家一同守望的事……"
            placeholderTextColor={colors.muted}
            style={[styles.input, styles.textarea]}
            multiline
            textAlignVertical="top"
            maxLength={500}
          />
          <Text style={styles.count}>{body.length}/500</Text>
          <View style={styles.consentRow}>
            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: accepted }}
              accessibilityLabel="同意祷告社区守则"
              hitSlop={6}
              onPress={() => setAccepted((value) => !value)}
              style={[styles.checkbox, accepted && styles.checkboxChecked]}
            >
              {accepted && (
                <Ionicons name="checkmark" size={17} color={colors.white} />
              )}
            </Pressable>
            <Text style={styles.consentText}>我同意保护个人隐私并遵守</Text>
            <Pressable
              accessibilityRole="link"
              hitSlop={6}
              onPress={onOpenGuidelines}
              disabled={!onOpenGuidelines}
            >
              <Text style={styles.link}>社区守则</Text>
            </Pressable>
          </View>
          {!canPublish && (title.length > 0 || body.length > 0) && (
            <Text style={styles.validation}>
              主题至少 4 个字、内容至少 8 个字，并需同意社区守则。
            </Text>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );

  if (!asModal) return content;
  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={close}
    >
      {content}
    </Modal>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  modal: { flex: 1, backgroundColor: colors.cream },
  header: {
    height: 60,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.line,
  },
  headerTitle: { fontSize: 16, fontWeight: "700", color: colors.ink },
  cancel: { fontSize: 15, color: colors.inkSoft, minWidth: 44 },
  publish: {
    fontSize: 15,
    color: colors.green,
    fontWeight: "800",
    textAlign: "right",
    minWidth: 44,
  },
  disabled: { opacity: 0.38 },
  form: { padding: 24, paddingBottom: 48 },
  formIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.mint,
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "center",
  },
  title: {
    fontSize: 22,
    fontWeight: "700",
    color: colors.ink,
    textAlign: "center",
    marginTop: 14,
  },
  hint: {
    fontSize: 13,
    lineHeight: 20,
    color: colors.inkSoft,
    textAlign: "center",
    marginTop: 7,
    marginBottom: 24,
  },
  label: {
    fontSize: 13,
    fontWeight: "700",
    color: colors.ink,
    marginBottom: 8,
    marginTop: 14,
  },
  categories: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  category: {
    minHeight: 44,
    paddingHorizontal: 18,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
  },
  categoryActive: { backgroundColor: colors.green, borderColor: colors.green },
  categoryText: { fontSize: 13, color: colors.inkSoft, fontWeight: "600" },
  categoryTextActive: { color: colors.white },
  input: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    minHeight: 52,
    paddingHorizontal: 15,
    fontSize: 15,
    color: colors.ink,
  },
  textarea: { height: 150, paddingTop: 14 },
  count: {
    fontSize: 12,
    color: colors.inkSoft,
    textAlign: "right",
    marginTop: 6,
  },
  validation: {
    color: "#A84535",
    fontSize: 12,
    textAlign: "right",
    marginTop: 5,
  },
  consentRow: {
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 12,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: "#8AA99E",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.white,
  },
  checkboxChecked: { backgroundColor: colors.green, borderColor: colors.green },
  consentText: { color: colors.inkSoft, fontSize: 13 },
  link: {
    color: colors.green,
    fontSize: 13,
    fontWeight: "700",
    textDecorationLine: "underline",
  },
});
