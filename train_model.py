# Model used: RandomForestClassifier (classification), not Linear Regression.
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from joblib import dump


def clamp_numeric(series: pd.Series, lower: float, upper: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    values = values.fillna(values.median())
    return values.clip(lower=lower, upper=upper)


# Load data
df = pd.read_csv("student_performance_prediction.csv")

# Build marks columns if dataset is still on the old schema
if "Internal Marks" not in df.columns:
    if "Attendance Rate" in df.columns:
        attendance = pd.to_numeric(df["Attendance Rate"], errors="coerce").clip(0, 100)
        df["Internal Marks"] = attendance.fillna(50) / 2
    else:
        df["Internal Marks"] = 25

if "Semester Exam Marks" not in df.columns:
    if "Previous Grades" in df.columns:
        df["Semester Exam Marks"] = pd.to_numeric(
            df["Previous Grades"], errors="coerce"
        ).clip(0, 100)
        df["Semester Exam Marks"] = df["Semester Exam Marks"].fillna(50)
    else:
        df["Semester Exam Marks"] = 50

# Ensure marks columns exist and are in expected ranges
df["Internal Marks"] = clamp_numeric(df.get("Internal Marks"), 0, 50)
df["Semester Exam Marks"] = clamp_numeric(df.get("Semester Exam Marks"), 0, 100)
df["Total Marks"] = df["Internal Marks"] + df["Semester Exam Marks"]

# Use label column directly when available to avoid training target leakage.
if "Passed" in df.columns:
    passed_text = df["Passed"].astype(str).str.strip().str.lower()
    valid_mask = passed_text.isin(["yes", "no", "1", "0", "true", "false"])
    df = df[valid_mask].copy()
    passed_text = df["Passed"].astype(str).str.strip().str.lower()
    df["Passed"] = passed_text.map(
        {"yes": 1, "no": 0, "1": 1, "0": 0, "true": 1, "false": 0}
    )
else:
    # Fallback only if label is absent.
    df["Passed"] = (df["Total Marks"] >= 75).map({True: 1, False: 0})

# Drop non-predictive ID column if present
if "Student ID" in df.columns:
    df = df.drop(columns=["Student ID"])

# Features/target
X = df.drop(columns=["Passed"])
y = df["Passed"]

# Remove direct target-construction columns to reduce leakage.
leakage_cols = ["Total Marks", "Internal Marks", "Semester Exam Marks"]
X = X.drop(columns=[c for c in leakage_cols if c in X.columns])

# Identify categorical and numerical columns from current dataset
categorical_cols = X.select_dtypes(include=["object"]).columns.tolist()
numerical_cols = [col for col in X.columns if col not in categorical_cols]

# Encode categoricals
label_encoders = {}
for col in categorical_cols:
    mode = X[col].mode()
    fill_value = mode.iloc[0] if not mode.empty else "unknown"
    X[col] = X[col].fillna(fill_value)
    le = LabelEncoder()
    X[col] = le.fit_transform(X[col])
    label_encoders[col] = le

# Clean numericals
for col in numerical_cols:
    X[col] = pd.to_numeric(X[col], errors="coerce")
    X[col] = X[col].fillna(X[col].mean())

# Train model
# Stratify to preserve class ratio in train/test.
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Apply SMOTE only on training data to avoid leakage from test to train.
minority_count = y_train.value_counts().min()
if minority_count > 1:
    k_neighbors = min(5, minority_count - 1)
    smote = SMOTE(random_state=42, k_neighbors=k_neighbors)
    X_train_balanced, y_train_balanced = smote.fit_resample(X_train, y_train)
else:
    # If minority class is too small for SMOTE, fall back to original split.
    X_train_balanced, y_train_balanced = X_train, y_train

# With SMOTE balancing, default class weighting avoids over-correction.
model = RandomForestClassifier(random_state=42)
model.fit(X_train_balanced, y_train_balanced)

# Save model bundle
model_bundle = {
    "model": model,
    "columns": X.columns.tolist(),
    "categorical_cols": categorical_cols,
    "label_encoders": label_encoders,
}
dump(model_bundle, "student_performance_model.joblib")

print("Model trained with SMOTE and saved as student_performance_model.joblib")
