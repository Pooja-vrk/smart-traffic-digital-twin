import React, { useState, useEffect } from 'react';
import { getPredictionStatus, getCurrentPrediction } from '../services/api';
import { calculateCongestionScore, classifyCongestion, getCongestionColor, getCongestionLabel } from '../utils/formatters';

const CongestionCard = ({ trafficData }) => {
  const [predictionStatus, setPredictionStatus] = useState(null);
  const [currentPrediction, setCurrentPrediction] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPredictionData();
  }, []);

  const loadPredictionData = async () => {
    try {
      setLoading(true);
      const [status, prediction] = await Promise.all([
        getPredictionStatus(),
        getCurrentPrediction().catch(() => null),
      ]);
      setPredictionStatus(status);
      setCurrentPrediction(prediction);
    } catch (error) {
      console.error('Failed to load prediction data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="card congestion-card">
        <h3 className="congestion-card-title">Congestion Status</h3>
        <div className="loading">Loading...</div>
      </div>
    );
  }

  const currentScore = trafficData ? calculateCongestionScore(
    trafficData.queues,
    trafficData.waiting,
    trafficData.speed
  ) : null;
  const currentLevel = classifyCongestion(currentScore);
  const currentColor = getCongestionColor(currentLevel);
  const currentLabel = currentScore !== null ? getCongestionLabel(currentLevel) : 'No Live Data';

  const modelAvailable = predictionStatus?.model_available || false;
  const predictedScore = typeof currentPrediction?.predicted_congestion_score === 'number'
    ? currentPrediction.predicted_congestion_score
    : null;
  const predictedLevel = currentPrediction?.congestion_level || 'UNKNOWN';
  const predictedColor = getCongestionColor(predictedLevel);
  const predictedLabel = getCongestionLabel(predictedLevel);
  const horizon = currentPrediction?.prediction_horizon || 30;

  return (
    <div className="card congestion-card">
      <h3 className="congestion-card-title">Congestion Status</h3>
      
      <div className="congestion-card-content">
        <div className="congestion-current">
          <div className="congestion-label">Current Congestion</div>
          <div className="congestion-score-display">
            <div className="congestion-score" style={{ color: currentColor }}>
              {currentScore !== null ? currentScore.toFixed(1) : '--'}
            </div>
            <div className="congestion-level" style={{ color: currentColor }}>
              {currentLabel}
            </div>
          </div>
        </div>

        {modelAvailable && currentPrediction ? (
          <div className="congestion-prediction">
            <div className="congestion-label">
              Predicted Congestion ({horizon}s)
            </div>
            <div className="congestion-score-display">
              <div className="congestion-score" style={{ color: predictedColor }}>
                {predictedScore !== null ? predictedScore.toFixed(1) : '--'}
              </div>
              <div className="congestion-level" style={{ color: predictedColor }}>
                {predictedLabel}
              </div>
            </div>
          </div>
        ) : (
          <div className="congestion-unavailable">
            <div className="congestion-unavailable-message">
              Prediction unavailable
            </div>
            <div className="congestion-unavailable-reason">
              {predictionStatus?.message || 'Historical data insufficient for training'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CongestionCard;
