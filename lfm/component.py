import asyncio
from datetime import timedelta
from typing import Any, cast, Set, Union


from tools.message.abstract import validate_json
from tools.components import AbstractSimulationComponent
from tools.exceptions.messages import MessageError
from tools.messages import BaseMessage,StatusMessage,EpochMessage
from tools.tools import FullLogger, load_environmental_variables, log_exception
from tools.message.block import TimeSeriesBlock, ValueArrayBlock
from tools.datetime_tools import to_utc_datetime_object

# import all the required messages from installed libraries
from domain_messages.Offer import OfferMessage
from domain_messages.Request import RequestMessage
from domain_messages.LFMMarketResult import LFMMarketResultMessage
from LFMmessages.FlexibilityNeedMessage import FlexibilityNeedMessage
from LFMmessages.LFMOfferingMessage import LFMOfferingMessage
from LFMmessages.SelectedOfferMessage import SelectedOfferMessage

# initialize logging object for the module
LOGGER = FullLogger(__name__)

# time interval in seconds on how often to check whether the component is still running
TIMEOUT = 1.0

# env var names
MARKET_OPENING_TIME = "MarketOpeningTime"
MARKET_CLOSING_TIME = "MarketClosingTime"
FLEXIBILITY_PROVIDER_LIST = "FlexibilityProviderList"
FLEXIBILITY_PROCURER_LIST = "FlexibilityProcurerList"

# Topics to listen
FLEXNEED_TOPIC_PREFIX = "FlexibilityNeed."
OFFER_TOPIC_PREFIX = "Offer."
SELOFFER_TOPIC_PREFIX = "SelectedOffer."

#
# UGLYFIX:
# Instead of listening Status.Ready topic to determine
# readiness of procurers this component listens separate
# topic. In this topic the procurers publish a copy of their
# status message.
#
# Listening to Status.Ready topic caused indeterministic error
# at simulation startup
#
PGO_READY_TOPIC_PREFIX = "PgoReady."

# Topics to publish
REQ_TOPIC_PREFIX = "Request."
MOFFER_TOPIC_PREFIX = "LFMOffering."
MRESULT_TOPIC_PREFIX = "LFMMarketResult."

class LFM(AbstractSimulationComponent):
    """
    This is procem LFM component, see wiki for proper description.
    """
    def __init__(self, procurers: str, producers, market_open_hour, market_closing_hour):
        # This will initialize various variables including the message client for message bus access.
        LOGGER.info("LFM constructor: procurers: {}".format(procurers))
        LOGGER.info("LFM constructor: produrers: {}".format(producers))
        super().__init__()

        self._other_topics = [
            FLEXNEED_TOPIC_PREFIX + self.component_name,
            OFFER_TOPIC_PREFIX + self.component_name,
            SELOFFER_TOPIC_PREFIX + self.component_name
        ]

        self._procurers = procurers.split(",")
        self._producers = producers.split(",")

        LOGGER.info("procurer list is:{}".format(self._procurers))
        LOGGER.info("producer list is:{}".format(self._producers))

        for procurer in self._procurers:
            self._other_topics.append( PGO_READY_TOPIC_PREFIX + procurer)

        self._market_open_hour = market_open_hour
        self._market_closing_hour = market_closing_hour

        self._market_result_topic = MRESULT_TOPIC_PREFIX + self.component_name
        self._request_topic = REQ_TOPIC_PREFIX + self.component_name
        self._market_offering_topic = MOFFER_TOPIC_PREFIX

        self._received_offer_count = {}
        self._expected_offer_count = {}
        self._procurersReady = {}

        for producer in self._producers:
            self._received_offer_count[producer] = 0
            self._expected_offer_count[producer] = None
        for procurer in self._procurers:
            self._procurersReady[procurer] = False

        #list of received flexibility need msgs
        self._needs = []
        #list of received offer msgs need msgs
        self._offers = []
        #list of accepted offer msgs need msgs
        self._results = []

        self._initial_message_send = False
        self._epoch_offering_sent = False

    def clear_epoch_variables(self) -> None:
        """Clears all the variables that are used to store information about the received input within the
           current epoch. This method is called automatically after receiving an epoch message for a new epoch.

           In LFM:
        """
        self._epoch_startime = to_utc_datetime_object(self._latest_epoch_message.start_time)
        self._epoch_endtime = to_utc_datetime_object(self._latest_epoch_message.end_time)

        #remove outdated results, needs and offers
        self._purgeOutdated()

        for need in self._needs:
            self._received_offer_count[need.congestion_id] = {}
            self._expected_offer_count[need.congestion_id] = {}
            for producer in self._producers:
                self._received_offer_count[need.congestion_id][producer] = 0
                self._expected_offer_count[need.congestion_id][producer] = None

        for procurer in self._procurers:
            self._procurersReady[procurer] = False

        self._initial_message_send = False
        self._epoch_LFMoffering_sent = False

    async def process_epoch(self) -> bool:
        LOGGER.info("Processing epoch")
        LOGGER.info("	Status: open flexneeds {}, open offers {}, market results {}".format(len(self._needs),len(self._offers),len(self._results)))

        if not self._initial_message_send:
            LOGGER.info("	Sending current Market Result")
            await self._publishMarketResults()

            if self._marketOpen():
                #await self._publishOpenOffers()
                await self._publishOpenRequests()
            self._initial_message_send = True

        if not self._marketOpen():
            LOGGER.info("	Market not open, epoch completed")
            return True


        all_producers_ready = True
        for need in self._needs:
            for producer in self._producers:
                if self._received_offer_count[need.congestion_id][producer] != self._expected_offer_count[need.congestion_id][producer]:

                    LOGGER.info("	Producer {} status: not ready | expected {} offers for need {}, got {}".format(producer, self._expected_offer_count[producer], need.congestion_id, self._received_offer_count[producer]))

                    all_producers_ready = False
        if len(self._needs) == 0:
            all_producers_ready = False

        all_procurers_ready = True
        for procurer in self._procurersReady:
            if not self._procurersReady[procurer]:
                all_procurers_ready = False


        if (all_producers_ready and all_procurers_ready) :
            LOGGER.info("Everyone is ready - Epoch Done")
            return True
        elif (all_procurers_ready and (len(self._needs) == 0)):
            LOGGER.info("Procurers are ready and no open FlexNeeds - Epoch Done")
            return True
        elif( all_producers_ready and not self._epoch_LFMoffering_sent ):
            LOGGER.info("Produrers are ready, sending LFMOffering - Epoch Not Done")
            await self._publishOpenOffers()
            self._epoch_LFMoffering_sent = True
            return False
        elif( all_producers_ready and self._epoch_LFMoffering_sent):
            LOGGER.info("Produrers are ready, LFMOffering already sent - Epoch Not Done")
            return False
        else:
            LOGGER.info("Participants not ready - Epoch Not Done")
            return False
        #
        #
        #
        #
        #if all_producers_ready and not self._epoch_offering_sent:
        #	await self._publishOpenOffers()
        #	self._epoch_offering_sent = True
        #
        #
        #
        #
        #
        #if (all_producers_ready and all_procurers_ready or :
        #	LOGGER.info("Epoch Done")
        #	#self._handle_msgs = False
        #	return True
        #else:
        #	LOGGER.info("Epoch not ready")
        #	return False


    async def all_messages_received_for_epoch(self) -> bool:
        """

        """
        return True


    async def general_message_handler(self, message_object: Union[BaseMessage, Any],
                                      message_routing_key: str) -> None:
        LOGGER.info("general_message_handler: begin general_message_handler")

        if self._latest_epoch == 0:
            LOGGER.info("general_message_handler: handler called in epoch 0 - exiting handler")
            return
        if self._completed_epoch == self._latest_epoch:
            LOGGER.info("general_message_handler: epoch already done - exiting handler")
            return

        if isinstance(message_object,FlexibilityNeedMessage):
            LOGGER.info("general_message_handler: Handling Flexneed msg")

            LOGGER.info("general_message_handler: Appending need to list")
            self._needs.append( message_object )

            #add the new need to expected offers list
            self._received_offer_count[message_object.congestion_id] = {}
            self._expected_offer_count[message_object.congestion_id] = {}
            for producer in self._producers:
                self._received_offer_count[message_object.congestion_id][producer] = 0
                self._expected_offer_count[message_object.congestion_id][producer] = None

            LOGGER.info("general_message_handler: Append msg id to trigger list")
            self._triggering_message_ids.append(message_object.message_id)
            await self._publishRequest( message_object )

            await self.start_epoch()

        elif isinstance(message_object,OfferMessage):
            LOGGER.info("general_message_handler: Handling Offer msg")

            producer = message_object.source_process_id
            congestion_id = message_object.congestion_id

            LOGGER.info("self._expected_offer_count[congestion_id][producer] is :{}".format(self._expected_offer_count[congestion_id][producer]))

            if self._expected_offer_count[congestion_id][producer] is None:
                self._expected_offer_count[congestion_id][producer] = message_object.offer_count

            if message_object.offer_count != 0:
                self._offers.append( message_object )
                self._received_offer_count[congestion_id][producer] = self._received_offer_count[congestion_id][producer] + 1

                self._triggering_message_ids.append(message_object.message_id)
                #await self._publishOffer( message_object )

            await self.start_epoch()

        elif isinstance(message_object, SelectedOfferMessage):
            LOGGER.info("general_message_handler: Handling SelectedOffer msg")

            LOGGER.info("general_message_handler:	selected offer id: {}".format(message_object.offer_ids))

            for selectedOfferId in message_object.offer_ids:
                for offerIndex in range( len(self._offers) ):

                    if self._offers[offerIndex] == None:
                        continue
                    if self._offers[offerIndex].offer_id == selectedOfferId:
                        LOGGER.info("general_message_handler:	found selected offer {}")

                        self._results.append( self._offers[offerIndex])
                        self._offers[offerIndex] = None

            LOGGER.info("general_message_handler:	deleting open offers")
            while None in self._offers:
                self._offers.remove(None)

            LOGGER.info("general_message_handler:	publishing market result")
            self._triggering_message_ids.append(message_object.message_id)
            await self._publishMarketResults()

            await self.start_epoch()

        elif isinstance(message_object,StatusMessage):
            LOGGER.info("general_message_handler: Handling Status msg")
            source_process_id = message_object.source_process_id
            if source_process_id in self._procurers:
                LOGGER.info("general_message_handler: Procurer {} has reported ready".format(source_process_id))
                self._procurersReady[source_process_id] = True

            if not self._completed_epoch == self._latest_epoch:
                await self.start_epoch()
        else:
            LOGGER.info("general_message_handler: Received unknown message from {}: {}".format(message_routing_key, message_object))
        LOGGER.info("general_message_handler: ended general_message_handler")

    async def _publishRequest( self, flexneed_msg: FlexibilityNeedMessage ):
        LOGGER.info("_publishRequest: Generating Request msg")
        result_msg = self._message_generator.get_message(
            RequestMessage,
            EpochNumber=self._latest_epoch,
            TriggeringMessageIds=self._triggering_message_ids,
            ActivationTime=flexneed_msg.activation_time,
            Duration=flexneed_msg.duration,
            Direction=flexneed_msg.direction,
            RealPowerMin=flexneed_msg.real_power_min,
            RealPowerRequest=flexneed_msg.real_power_request,
            CongestionId=flexneed_msg.congestion_id,
            CustomerIds=flexneed_msg.customer_ids,
            BidResolution=flexneed_msg.bid_resolution
        )

        LOGGER.info("_publishRequest: Publishing Request msg")
        await self._rabbitmq_client.send_message(
            topic_name=self._request_topic,
            message_bytes=result_msg.bytes()
        )
        LOGGER.info("_publishRequest: Done")

    async def _publishOpenRequests(self):
        for index in range( len( self._needs ) ):
            await self._publishRequest(self._needs[index])

    async def _publishOpenOffers(self):
        for procurer in self._procurers:
            for need in self._needs:
                LOGGER.info("_publishOpenOffers: findin LFM offering for: {}, congestion_id {}".format( procurer, need.congestion_id) )

                if need.source_process_id == procurer:
                    offer_count = 0
                    for offer in self._offers:
                        if offer.congestion_id == need.congestion_id and offer.offer_count != 0:
                            offer_count = offer_count + 1

                    LOGGER.info("_publishOpenOffers: found {} non-zero offers".format( offer_count ) )

                    if offer_count == 0:
                        LOGGER.info("_publishOpenOffers: generating empty LFMOfferingMessage ")
                        result_msg = self._message_generator.get_message(
                            LFMOfferingMessage,
                            EpochNumber=self._latest_epoch,
                            TriggeringMessageIds=self._triggering_message_ids,
                            ActivationTime=None,
                            Duration=None,
                            Direction=None,
                            RealPower=None,
                            Price=None,
                            CongestionId=need.congestion_id,
                            OfferId=None,
                            OfferCount=offer_count,
                            CustomerIds=None,
                        )

                        LOGGER.info("_publishOpenOffers: Publishing empty LFMOffering msg")
                        await self._rabbitmq_client.send_message(
                            topic_name=self._market_offering_topic + procurer,
                            message_bytes=result_msg.bytes()
                        )

                    else:
                        for offer in self._offers:
                            if offer.congestion_id == need.congestion_id and offer.offer_count != 0:

                                LOGGER.info("_publishOpenOffers: generating LFMOfferingMessage for offer_id: {}".format( offer.offer_id ))
                                result_msg = self._message_generator.get_message(
                                    LFMOfferingMessage,
                                    EpochNumber=self._latest_epoch,
                                    TriggeringMessageIds=self._triggering_message_ids,
                                    ActivationTime=offer.activation_time,
                                    Duration=offer.duration,
                                    Direction=offer.direction,
                                    RealPower=offer.real_power,
                                    Price=offer.price.value,
                                    CongestionId=offer.congestion_id,
                                    OfferId=offer.offer_id,
                                    OfferCount=offer_count,
                                    CustomerIds=offer.customerids,
                                )

                                LOGGER.info("_publishOpenOffers: publishing LFMOfferingMessage for offer_id: {}".format( offer.offer_id ))
                                await self._rabbitmq_client.send_message(
                                    topic_name=self._market_offering_topic + procurer,
                                    message_bytes=result_msg.bytes()
                                )

    async def _publishMarketResult(self, result_index: int):
        LOGGER.info("_publishMarketResult: Generating LFMMarketResult msg")
        if result_index < 0:
            result_msg = self._message_generator.get_message(
                LFMMarketResultMessage,
                EpochNumber=self._latest_epoch,
                TriggeringMessageIds=self._triggering_message_ids,
                ActivationTime=None,
                Duration=None,
                Direction=None,
                RealPower=None,
                Price=None,
                CongestionId=None,
                OfferId=None,
                ResultCount=0,
                CustomerIds=None,
            )

            LOGGER.info("_publishMarketResult: Publishing empty LFMMarketResult msg")
            await self._rabbitmq_client.send_message(
                topic_name=self._market_result_topic,
                message_bytes=result_msg.bytes()
            )
        else:
            accepted_offer_msg = self._results[result_index]

            total_results = 0
            for msg in self._results:
                if msg.congestion_id == accepted_offer_msg.congestion_id:
                    total_results = total_results + 1


            result_msg = self._message_generator.get_message(
                LFMMarketResultMessage,
                EpochNumber=self._latest_epoch,
                TriggeringMessageIds=self._triggering_message_ids,
                ActivationTime=accepted_offer_msg.activation_time,
                Duration=accepted_offer_msg.duration,
                Direction=accepted_offer_msg.direction,
                RealPower=accepted_offer_msg.real_power,
                Price=accepted_offer_msg.price.value,
                CongestionId=accepted_offer_msg.congestion_id,
                OfferId=accepted_offer_msg.offer_id,
                ResultCount=total_results,
                CustomerIds=accepted_offer_msg.customerids,
            )

        LOGGER.info("_publishMarketResult: Publishing LFMMarketResult msg")
        await self._rabbitmq_client.send_message(
            topic_name=self._market_result_topic,
            message_bytes=result_msg.bytes()
        )
        LOGGER.info("_publishMarketResult: Done")

    async def _publishMarketResults(self):
        if len(self._results) == 0:
            await self._publishMarketResult(-1)
        else:
            for index in range( len( self._results ) ):
                await self._publishMarketResult(index)

    # def _purgeOutdated(self):
    #     for index in range( len( self._needs ) ):        # removing the needs that has a passed activation time
    #         need_actv_time = to_utc_datetime_object(self._needs[index].activation_time)
    #         if need_actv_time < self._epoch_endtime:
    #             self._needs[index]=None

    #     for index in range( len( self._offers ) ):      # removing offers that has a passed activation time
    #         offer_actv_time = to_utc_datetime_object(self._offers[index].activation_time)
    #         if offer_actv_time < self._epoch_endtime:
    #             self._offers[index]=None

    #     for index in range( len( self._results ) ):    # removing results that has passed
    #         result_actv_time = to_utc_datetime_object(self._results[index].activation_time)
    #         result_duration_seconds = self._results[index].duration.value * 60
    #         if result_actv_time + timedelta(seconds=result_duration_seconds)< self._epoch_endtime:
    #             self._results[index]=None

    #     while None in self._results:
    #         self._results.remove(None)
    #     while None in self._offers:
    #         self._offers.remove(None)
    #     while None in self._needs:
    #         self._needs.remove(None)

    def _purgeOutdated(self):
        for index in range( len( self._needs ) ):        # removing the needs in the beginning of an epoch
            self._needs[index]=None

        for index in range( len( self._offers ) ):      # removing offers in the beginning of an epoch
            self._offers[index]=None

        for index in range( len( self._results ) ):    # removing results in the beginning of an epoch
            self._results[index]=None

        while None in self._results:
            self._results.remove(None)
        while None in self._offers:
            self._offers.remove(None)
        while None in self._needs:
            self._needs.remove(None)

    def _marketOpen(self):
        #if self._epoch_startime.hour >= self._market_open_hour and self._epoch_endtime.hour <= self._market_closing_hour:
        #	return True
        #else:
        #	return False
        if self._epoch_startime.hour < self._market_open_hour or self._epoch_startime.hour > self._market_closing_hour:
            return False
        else:
            return True

def create_component() -> LFM:
    """
    Creates and returns the componet
    """
    environment_variables = load_environmental_variables(
        (MARKET_OPENING_TIME, float, 0),
        (MARKET_CLOSING_TIME, float, 0),
        (FLEXIBILITY_PROVIDER_LIST, str, ""),
        (FLEXIBILITY_PROCURER_LIST, str, "")
    )

    return LFM(
        procurers=environment_variables[FLEXIBILITY_PROCURER_LIST],
        producers=environment_variables[FLEXIBILITY_PROVIDER_LIST],
        market_open_hour=environment_variables[MARKET_OPENING_TIME],
        market_closing_hour=environment_variables[MARKET_CLOSING_TIME]
    )


async def start_component():
    """
    Creates and starts the component.
    """
    try:
        LFM_component = create_component()

        await LFM_component.start()

        while not LFM_component.is_stopped:
            await asyncio.sleep(TIMEOUT)

    except BaseException as error:	# pylint: disable=broad-except
        log_exception(error)
        LOGGER.info("Component will now exit.")


if __name__ == "__main__":
    asyncio.run(start_component())
