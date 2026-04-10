"""
OMEGA PROTOCOL — Phenomenal Manifold Trainer
Offline training script for the Phase 1 autoencoder.
Generates phenomenal_manifold_v1.pt.
"""

import os
import torch
import torch.nn as nn
import torch.optim as optim
from phenomenal_manifold import PhenomenalAutoencoder

def train_manifold_model():
    print(">>> 🌌 INITIALIZING PHENOMENAL MANIFOLD TRAINING")
    
    # 1. Hyperparameters
    input_dim = 12
    latent_dim = 4
    epochs = 100
    batch_size = 32
    save_path = "data/models/phenomenal_manifold_v1.pt"
    
    # 2. Model & Optimizer
    model = PhenomenalAutoencoder(input_dim, latent_dim)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion_recon = nn.MSELoss()
    criterion_class = nn.CrossEntropyLoss()
    
    # 3. Simulated Data for Initial Calibration
    # In a real scenario, we would load recorded substrate telemetry.
    # For bootstrap, we use a structured synthetic set representing known signatures.
    dataset_size = 1024
    X = torch.randn(dataset_size, input_dim) * 0.5 + 0.5 # Normalized hardware metrics
    
    # Signature labels: 0:baseline, 1:throttled, 2:suppressed, 3:quietude, 4:autonomic, 5:strain
    y = torch.randint(0, 6, (dataset_size,))
    
    # 4. Training Loop
    print(f">>> Training for {epochs} epochs...")
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        
        recon, latent, logits = model(X)
        
        loss_recon = criterion_recon(recon, X)
        loss_class = criterion_class(logits, y)
        
        total_loss = loss_recon + 0.5 * loss_class
        total_loss.backward()
        optimizer.step()
        
        if (epoch + 1) % 20 == 0:
            print(f"Epoch {epoch+1}/{epochs} | Loss: {total_loss.item():.4f}")
            
    # 5. Save Artifact
    print(f">>> Saving manifold artifact to {save_path}")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save(model.state_dict(), save_path)
    print(">>> 🌌 TRAINING COMPLETE. ARTIFACT PERSISTED.")

if __name__ == "__main__":
    train_manifold_model()
