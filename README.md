# Local flexibility market (LFM)

Author:

> Antti Supponen, Mehdi Attar
>
> Tampere University
>
> Finland

**Introduction**

The local flexibility market (LFM) acts as a bridge between flexibility providers (e.g., prosumers, aggregators, energy communities (EC)) and flexibility buyers (mainly distribution system operators (DSO)).

The component is only deployable in the [SimCES ](https://simcesplatform.github.io/)platform.

**Workflow of the LFM**

1. LFM receives the flexibility requests from the flexibility buyers.
2. LFM publishes the flexibility requests to all flexibility providers.
3. LFM receives the flexibility providers' bids.
4. LFM gathers all the submitted bids and send them to the flexibility buyers.
5. LFM receives the selected bids from the flexibility buyers.
6. LFM shares the market results to all market participants.

**Epoch workflow**

In beginning of the simulation the LFM component will wait for [SimState](https://simcesplatform.github.io/core_msg-simstate/)(running) message, when the message is received component will initialize and send [Status](https://simcesplatform.github.io/core_msg-status/)(Ready) message with epoch number 0. If SimState(stopped) is received component will close down. Other message are ignored at this stage.

After startup component will begin to listen for [epoch](https://simcesplatform.github.io/core_msg-epoch/) messages. In the first epoch of simulation run the component will publish initialization message. Initialization message is published for mostly informative purposes for participants. It contains the MarketId and opening and closing times of the market in the simulation run.

If the running epoch is not within the market window component it will send [ready](https://simcesplatform.github.io/core_msg-status/#ready-message) message, and continues to wait for next epoch message. Other messages will be ignored at this stage.

If the running epoch is within the market window component will first send [Request ](https://simcesplatform.github.io/energy_msg-request/)and [LFMOffering](https://simcesplatform.github.io/energy_msg-lfmoffering/) messages of all open flexibility transactions during running market window. If this is the first epoch of market window, or no open transactions from previous market epoch exists, no messages are sent.

When component receives a [FlexibilityNeed](https://simcesplatform.github.io/energy_msg-flexibilityneed/) message in market epoch it will internally open new flexibility transaction and send out corresponding [Request ](https://simcesplatform.github.io/energy_msg-request/)message(s).

When component receives an [Offer](https://simcesplatform.github.io/energy_msg-offer/) message it creates on open internal Bid which is linked an existing open Transaction. Then component send corresponding [LFMOffering ](https://simcesplatform.github.io/energy_msg-lfmoffering/)message. If an Offer message is received that does not link to an existing Transaction it will be ignored without warning.

When component receives a [SelectedOffer](https://simcesplatform.github.io/energy_msg-selectedoffer/) message, the corresponding Bid is deleted and new market result is added. [LFMmarketResult](https://simcesplatform.github.io/energy_msg-lfmmarketresult/) message is sent if all offer messages are received. Transaction will remain open until the end of the market window.

If at any stage of the execution Status (Error) message is received component will immediately close down

**Implementation details**

- Language and platform

| Programming language | Python                                               |
| -------------------- | ---------------------------------------------------- |
| Platform             | Python 3.8.3                                         |
| Operating system     | Docker Ubuntu (give image name and version), Windows |

**External packages**

The following packages are needed.

| Package          | Version   | Why needed                                                                                | URL                                                |
| ---------------- | --------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Simulation Tools | (Unknown) | "Tools for working with simulation messages and with the RabbitMQ message bus in Python." | https://github.com/simcesplatform/simulation-tools |
