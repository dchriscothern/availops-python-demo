"""
AvailOps — Availability Operations System
Machine Learning (Optional) for Availability Risk Flagging and Readiness Scoring
"""

import pandas as pd
import numpy as np
import sqlite3
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
import pickle
import os
from datetime import timedelta

class AvailabilityRiskScorer:
    """Score short-horizon availability risk (demo) based on recent trends."""
    
    def __init__(self, db_path='availops_demo.db'):
        self.db_path = db_path
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        
    def create_training_data(self):
        """Create labeled dataset with features and unavailability outcomes (demo)"""
        
        print("Creating training dataset...")
        conn = sqlite3.connect(self.db_path)
        
        # Get all unavailability events (demo)
        injuries = pd.read_sql_query(
            "SELECT player_id, injury_date FROM injuries", 
            conn,
            parse_dates=['injury_date']
        )
        
        # Get all player-date combinations
        query = """
            SELECT 
                p.player_id,
                p.position,
                p.age,
                p.injury_history_count,
                w.date,
                w.sleep_hours,
                w.sleep_quality,
                w.soreness,
                w.stress,
                w.mood,
                t.practice_minutes,
                t.practice_rpe,
                t.strength_volume,
                t.game_minutes,
                a.acwr,
                f.asymmetry_percent,
                f.cmj_height_cm,
                f.rsi_modified
            FROM players p
            JOIN wellness w ON p.player_id = w.player_id
            JOIN training_load t ON p.player_id = t.player_id AND w.date = t.date
            LEFT JOIN acwr a ON p.player_id = a.player_id AND w.date = a.date
            LEFT JOIN force_plate f ON p.player_id = f.player_id AND w.date = f.date
        """
        
        data = pd.read_sql_query(query, conn, parse_dates=['date'])
        conn.close()
        
        # Create rolling averages (7-day windows)
        data = data.sort_values(['player_id', 'date'])
        
        for col in ['sleep_hours', 'soreness', 'stress', 'game_minutes']:
            data[f'{col}_7day_avg'] = data.groupby('player_id')[col].transform(
                lambda x: x.rolling(7, min_periods=1).mean()
            )
        
        # Create target: injury within next 7 days
        data['unavailable_within_7days'] = 0
        
        for _, injury in injuries.iterrows():
            injury_window_start = injury['injury_date'] - timedelta(days=7)
            injury_window_end = injury['injury_date']
            
            mask = (
                (data['player_id'] == injury['player_id']) &
                (data['date'] >= injury_window_start) &
                (data['date'] <= injury_window_end)
            )
            data.loc[mask, 'unavailable_within_7days'] = 1
        
        print(f"Total samples: {len(data)}")
        print(f"Injury samples: {data['unavailable_within_7days'].sum()}")
        print(f"Non-injury samples: {(data['unavailable_within_7days'] == 0).sum()}")
        
        return data
    
    def prepare_features(self, data):
        """Prepare feature matrix and target"""
        
        # Select features
        feature_cols = [
            'age', 'injury_history_count',
            'sleep_hours', 'sleep_quality', 'soreness', 'stress', 'mood',
            'sleep_hours_7day_avg', 'soreness_7day_avg', 'stress_7day_avg',
            'practice_minutes', 'practice_rpe', 'strength_volume', 'game_minutes',
            'game_minutes_7day_avg', 'acwr', 'asymmetry_percent',
            'cmj_height_cm', 'rsi_modified'
        ]
        
        # Handle missing values
        data_clean = data[feature_cols + ['unavailable_within_7days']].copy()
        data_clean = data_clean.fillna(data_clean.mean())
        
        # Encode position as dummy variables
        position_dummies = pd.get_dummies(data['position'], prefix='position')
        data_clean = pd.concat([data_clean, position_dummies], axis=1)
        
        feature_cols += list(position_dummies.columns)
        
        X = data_clean[feature_cols]
        y = data_clean['unavailable_within_7days']
        
        self.feature_names = feature_cols
        
        return X, y
    
    def train(self):
        """Train the injury prediction model"""
        
        # Create dataset
        data = self.create_training_data()
        X, y = self.prepare_features(data)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        print("\nTraining Gradient Boosting Classifier...")
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=4,
            random_state=42
        )
        
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        y_pred_proba = self.model.predict_proba(X_test_scaled)[:, 1]
        
        print("\n=== MODEL EVALUATION ===")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=['No Injury', 'Injury']))
        
        print("\nConfusion Matrix:")
        print(confusion_matrix(y_test, y_pred))
        
        try:
            auc_score = roc_auc_score(y_test, y_pred_proba)
            print(f"\nAUC-ROC Score: {auc_score:.3f}")
        except:
            print("\nCould not calculate AUC-ROC (not enough positive samples)")
        
        # Feature importance
        print("\n=== TOP 10 FEATURE IMPORTANCE ===")
        feature_importance = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        print(feature_importance.head(10).to_string(index=False))
        
        return feature_importance
    
    def predict_risk(self, player_data):
        """Predict injury risk for a player"""
        
        player_features = player_data[self.feature_names].copy()
        
        # Fill NaN values with 0 (conservative approach for missing data)
        player_features = player_features.fillna(0)
        
        # Ensure all values are numeric
        player_features = player_features.astype(float)
        
        player_features_scaled = self.scaler.transform(player_features)
        
        risk_proba = self.model.predict_proba(player_features_scaled)[:, 1]
        risk_score = risk_proba * 100  # Convert to percentage
        
        # Categorize risk
        risk_category = np.where(
            risk_score < 30, 'Low',
            np.where(risk_score < 60, 'Medium', 'High')
        )
        
        return risk_score, risk_category
    
    def save_model(self, filepath='availops_risk_model.pkl'):
        """Save trained model"""
        with open(filepath, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'scaler': self.scaler,
                'feature_names': self.feature_names
            }, f)
        print(f"\nModel saved to {filepath}")
    
    def load_model(self, filepath='availops_risk_model.pkl'):
        """Load trained model"""
        with open(filepath, 'rb') as f:
            saved = pickle.load(f)
            self.model = saved['model']
            self.scaler = saved['scaler']
            self.feature_names = saved['feature_names']
        print(f"Model loaded from {filepath}")


class ReadinessScorer:
    """Calculate daily readiness score from multiple inputs"""
    
    def __init__(self, db_path='availops_demo.db'):
        self.db_path = db_path
    
    def calculate_readiness(self, player_id, date):
        """Calculate composite readiness score (0-100)"""
        
        conn = sqlite3.connect(self.db_path)
        
        # Get recent data
        query = f"""
            SELECT 
                w.sleep_hours,
                w.sleep_quality,
                w.soreness,
                w.stress,
                a.acwr,
                f.cmj_height_cm,
                f.asymmetry_percent
            FROM wellness w
            LEFT JOIN acwr a ON w.player_id = a.player_id AND w.date = a.date
            LEFT JOIN force_plate f ON w.player_id = f.player_id AND w.date = f.date
            WHERE w.player_id = {player_id}
            AND w.date = '{date}'
        """
        
        data = pd.read_sql_query(query, conn)
        conn.close()
        
        if len(data) == 0:
            return None
        
        row = data.iloc[0]
        
        # Component scores (0-100 each)
        
        # 1. Sleep score (30% weight)
        sleep_score = min(100, (row['sleep_hours'] / 8.0) * 100)
        sleep_quality_score = row['sleep_quality'] * 10
        sleep_component = (sleep_score * 0.6 + sleep_quality_score * 0.4)
        
        # 2. Wellness score (25% weight)
        soreness_score = (10 - row['soreness']) * 10
        stress_score = (10 - row['stress']) * 10
        wellness_component = (soreness_score * 0.6 + stress_score * 0.4)
        
        # 3. Load score (25% weight)
        if pd.notna(row['acwr']):
            # Optimal ACWR is 0.8-1.3
            if 0.8 <= row['acwr'] <= 1.3:
                load_score = 100
            elif row['acwr'] < 0.8:
                load_score = 70 + (row['acwr'] / 0.8) * 30
            else:  # acwr > 1.3
                load_score = max(0, 100 - (row['acwr'] - 1.3) * 50)
            load_component = load_score
        else:
            load_component = 75  # Default if no ACWR data
        
        # 4. Force plate score (20% weight) - only if tested that day
        if pd.notna(row['asymmetry_percent']):
            # Lower asymmetry is better
            asymmetry_score = max(0, 100 - row['asymmetry_percent'] * 3)
            force_component = asymmetry_score
        else:
            force_component = None  # Don't include if not tested
        
        # Calculate weighted average
        if force_component is not None:
            total_score = (
                sleep_component * 0.30 +
                wellness_component * 0.25 +
                load_component * 0.25 +
                force_component * 0.20
            )
        else:
            # Redistribute weight if no force plate data
            total_score = (
                sleep_component * 0.35 +
                wellness_component * 0.35 +
                load_component * 0.30
            )
        
        # Categorize readiness
        if total_score >= 80:
            category = 'High'
            recommendation = 'Ready for normal training load'
        elif total_score >= 60:
            category = 'Moderate'
            recommendation = 'Monitor closely, consider reducing volume'
        else:
            category = 'Low'
            recommendation = 'Recommend reduced load or active recovery'
        
        return {
            'readiness_score': round(total_score, 1),
            'category': category,
            'recommendation': recommendation,
            'components': {
                'sleep': round(sleep_component, 1),
                'wellness': round(wellness_component, 1),
                'load': round(load_component, 1),
                'force_plate': round(force_component, 1) if force_component else None
            }
        }
    
    def calculate_team_readiness(self, date):
        """Calculate readiness for entire team on a given date"""
        
        conn = sqlite3.connect(self.db_path)
        players = pd.read_sql_query("SELECT player_id, name FROM players", conn)
        conn.close()
        
        results = []
        for _, player in players.iterrows():
            readiness = self.calculate_readiness(player['player_id'], date)
            if readiness:
                results.append({
                    'player_id': player['player_id'],
                    'name': player['name'],
                    **readiness
                })
        
        return pd.DataFrame(results)


def main():
    os.makedirs('outputs', exist_ok=True)

    """Run ML model training and evaluation"""
    
    print("="*70)
    print("DALLAS WINGS AVAILABILITY INTELLIGENCE SYSTEM")
    print("Machine Learning Models - Training")
    print("="*70 + "\n")
    
    # Train injury risk model
    print("STEP 1: Training Injury Risk Prediction Model\n")
    predictor = AvailabilityRiskScorer()
    feature_importance = predictor.train()
    predictor.save_model('availops_risk_model.pkl')
    
    # Save feature importance
    feature_importance.to_csv('outputs/feature_importance.csv', index=False)
    print("\nFeature importance saved to outputs/feature_importance.csv")
    
    # Test readiness scorer
    print("\n" + "="*70)
    print("STEP 2: Testing Readiness Scorer\n")
    scorer = ReadinessScorer()
    
    # Calculate readiness for most recent date
    conn = sqlite3.connect('wings_availability.db')
    latest_date = pd.read_sql_query("SELECT MAX(date) as date FROM wellness", conn)['date'][0]
    conn.close()
    
    print(f"Calculating team readiness for: {latest_date}\n")
    team_readiness = scorer.calculate_team_readiness(latest_date)
    team_readiness = team_readiness.sort_values('readiness_score', ascending=False)
    
    print("=== TEAM READINESS REPORT ===\n")
    print(team_readiness[['name', 'readiness_score', 'category', 'recommendation']].to_string(index=False))
    
    # Save team readiness
    team_readiness.to_csv('outputs/team_readiness_latest.csv', index=False)
    print(f"\nTeam readiness saved to outputs/team_readiness_latest.csv")
    
    # Generate current risk predictions
    print("\n" + "="*70)
    print("STEP 3: Generating Current Injury Risk Predictions\n")
    
    # Get latest data for all players
    conn = sqlite3.connect('wings_availability.db')
    
    query = """
        SELECT 
            p.player_id,
            p.name,
            p.position,
            p.age,
            p.injury_history_count,
            w.date,
            w.sleep_hours,
            w.sleep_quality,
            w.soreness,
            w.stress,
            w.mood,
            t.practice_minutes,
            t.practice_rpe,
            t.strength_volume,
            t.game_minutes,
            a.acwr,
            f.asymmetry_percent,
            f.cmj_height_cm,
            f.rsi_modified
        FROM players p
        JOIN wellness w ON p.player_id = w.player_id
        JOIN training_load t ON p.player_id = t.player_id AND w.date = t.date
        LEFT JOIN acwr a ON p.player_id = a.player_id AND w.date = a.date
        LEFT JOIN force_plate f ON p.player_id = f.player_id AND w.date = f.date
        WHERE w.date = (SELECT MAX(date) FROM wellness)
    """
    
    current_data = pd.read_sql_query(query, conn, parse_dates=['date'])
    conn.close()
    
    # Get historical data for rolling averages
    conn2 = sqlite3.connect('wings_availability.db')
    hist_query = """
        SELECT 
            p.player_id,
            w.date,
            w.sleep_hours,
            w.soreness,
            w.stress,
            t.game_minutes
        FROM players p
        JOIN wellness w ON p.player_id = w.player_id
        JOIN training_load t ON p.player_id = t.player_id AND w.date = t.date
        WHERE w.date >= date((SELECT MAX(date) FROM wellness), '-7 days')
    """
    hist_data = pd.read_sql_query(hist_query, conn2, parse_dates=['date'])
    conn2.close()
    
    # Calculate 7-day rolling averages
    hist_data = hist_data.sort_values(['player_id', 'date'])
    for col in ['sleep_hours', 'soreness', 'stress', 'game_minutes']:
        hist_data[f'{col}_7day_avg'] = hist_data.groupby('player_id')[col].transform(
            lambda x: x.rolling(7, min_periods=1).mean()
        )
    
    # Get latest rolling averages for each player
    latest_avgs = hist_data.loc[hist_data.groupby('player_id')['date'].idxmax()]
    
    # Merge with current data
    current_data = current_data.merge(
        latest_avgs[['player_id', 'sleep_hours_7day_avg', 'soreness_7day_avg', 
                     'stress_7day_avg', 'game_minutes_7day_avg']], 
        on='player_id', 
        how='left'
    )
    
    # Add position dummies
    position_dummies = pd.get_dummies(current_data['position'], prefix='position')
    current_data = pd.concat([current_data, position_dummies], axis=1)
    
    # Fill all NaN values in numeric columns only
    numeric_cols = current_data.select_dtypes(include=[np.number]).columns
    current_data[numeric_cols] = current_data[numeric_cols].fillna(current_data[numeric_cols].mean())
    
    # Predict risk
    risk_scores, risk_categories = predictor.predict_risk(current_data)
    
    # Combine results
    risk_results = pd.DataFrame({
        'name': current_data['name'],
        'position': current_data['position'],
        'availability_risk_score': risk_scores.round(1),
        'risk_category': risk_categories,
        'soreness': current_data['soreness'],
        'sleep_hours': current_data['sleep_hours'],
        'acwr': current_data['acwr'].round(2)
    }).sort_values('availability_risk_score', ascending=False)
    
    print("=== CURRENT AVAILABILITY RISK (DEMO) ===\n")
    print(risk_results.to_string(index=False))
    
    # Save risk predictions
    risk_results.to_csv('outputs/current_availability_risk.csv', index=False)
    print("\nAvailability risk output saved to outputs/current_availability_risk.csv")
    
    print("\n" + "="*70)
    print("✅ MODEL BUILD COMPLETE (DEMO)")
    print("="*70)
    print("\nFiles created:")
    print("  - availops_risk_model.pkl (trained model)")
    print("  - outputs/feature_importance.csv (drivers)")
    print("  - outputs/team_readiness_latest.csv (readiness scores)")
    print("  - outputs/current_availability_risk.csv (risk output)")
    
    print("\n📊 Key Insights:")
    print(f"  - {len(risk_results[risk_results['risk_category'] == 'High'])} players flagged HIGH availability risk")
    print(f"  - {len(team_readiness[team_readiness['category'] == 'Low'])} players flagged LOW readiness")
    print(f"  - Average team readiness: {team_readiness['readiness_score'].mean():.1f}/100")

if __name__ == "__main__":
    main()
